#!/usr/bin/env python
# coding: utf-8
from __future__ import print_function, division
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
import getpass
import json
import optparse
import os
import random
import re
import requests
import time
import constants


def load_instagram(username = None):
    """
    Load selenium driver and log into your Instagram account
    """
    driver = webdriver.Chrome()
    driver.set_window_size(360,720)
    driver.set_window_position(400,0)
    driver.get('https://www.instagram.com/accounts/login')

    if username is not None:
        password = getpass.getpass('Password: ').rstrip()
        username_field = driver.find_element_by_name('username')
        password_field = driver.find_element_by_name('password')
        actions = ActionChains(driver).click(
                     username_field).send_keys(username).click(
                     password_field).send_keys(password).send_keys(Keys.RETURN)
        actions.perform()

    try:
        logged_in = WebDriverWait(driver, 30).until(
                        EC.presence_of_element_located(
                        (By.XPATH, './/a[contains(@class, "coreSpriteDesktopNavProfile")]'))
                    )
        print("I'm in!")
        return driver, True

    except TimeoutException:
        driver.quit()
        return _, False


class HeartGiver(object):

    def __init__(self, driver, tag_data='',
            ignore=[], thresh=3.0, get_top_posts=False, sliding_window = 3600.0,
            count_limit=60, min_engagements=20, max_engagements=100):
        self.driver = driver
        self.tag_data = tag_data
        self.ignore_tags = ignore
        self.thresh = thresh
        self.get_top_posts = get_top_posts
        self.sliding_window = sliding_window
        self.count_limit = count_limit
        self.window_counter = 0
        self.like_count = 0
        self.liked_posts = []
        self.min_engagements = min_engagements
        self.max_engagements = max_engagements

    def load_tags(self, filename=''):
        """ Parse textfile that contains hashtags and return list of tags
        """
        if filename:
            with open(filename, 'r') as f:
                raw_lines = f.readlines()
            tags_text = ' '.join([l for l in raw_lines if '#' in l])
            rx = re.compile(r'#(\w+)\s*(?:\r|\n)?', re.I)
            return rx.findall(tags_text)
        else:
            # Return popular tags by default
            return ['cute', 'love', 'lifestyle', 'fun', 'tbt', 'beautiful']

    def run(self, num_loops, num_tags):
        tags = self.load_tags(self.tag_data)
        self.worker(tags, num_loops, num_tags)

    def worker(self, tags, num_loops, num_tags):
        """ Worker explores tags every 10 minutes
        """
        start_time = time.time()
        i = 0
        while i < num_loops:
            if i != 0:
                time.sleep(600 - min(600, time.time() - start_time) % 601)
            print('Starting 10-min loop #{}/{}'.format(*map(str, (i + 1, num_loops))))
            random.shuffle(tags)

            for ti, tag in enumerate(tags[:num_tags], 1):
                if (time.time() - start_time) > self.sliding_window * self.window_counter:
                    self.window_counter += 1  # TO-DO: change this to mod (%)
                    self.like_count = 0  # one-hour window expired, so reset the like_count

                print("==> {}/{}: Now exploring #{}".format(ti, num_tags, tag))
                # self.driver.get("https://www.instagram.com/explore/tags/{}".format(tag))
                # WebDriverWait(self.driver, 5).until(
                #     EC.presence_of_element_located((By.CLASS_NAME, constants.tags_article_class))
                # )
                flag = self._like_post_by_tag(tag)
                if flag:
                    elapsed = ((time.time() - start_time) % self.sliding_window)
                    print("WARNING: Rate limit reached. Sleeping for {} seconds."
                          .format(str(self.sliding_window - elapsed)))
                    time.sleep(self.sliding_window - elapsed)
            print("Like count is {} in this one-hour sliding window.".format(str(self.like_count)))
            i += 1

    def _like_post_by_tag(self, tag):
        """
        Like likable posts by hashtag
        Likable post defined here is the post with engagements per minute > threshold ratio
        """
        limit_reached = False
        try:
            # loadmore_class = ['8imhp', 'oidfu']  # Two possible Load More as of February 2017
            # element = next((driver.find_element_by_css_selector('a._{}'.format(c)) for c in loadmore_class))
            # element.click()

            # Scroll down just enough for about 20 posts
            # for _ in range(5):
            #     self.driver.execute_script('window.scrollTo(0, document.body.scrollHeight);')
            #     time.sleep(0.5)

            posts = []
            likable_posts = []
            # Current limit: Top 9 + Recent 55 = 64 posts
            source = requests.get('http://www.instagram.com/explore/tags/{}'.format(tag)).content
            now = time.time()
            json_data = json.loads(re.findall(
                    r'<script type="text\/javascript">window._sharedData = (.*?);<\/script>',
                    source)[0]
                )
            media_data = json_data['entry_data']['TagPage'][0]['tag']
            top_media = media_data['top_posts']['nodes']
            recent_media = media_data['media']['nodes']
            mymedia = (top_media + recent_media) if self.get_top_posts else recent_media
            for post in mymedia:
                # Get post JSON data
                is_photo = not post['is_video']
                engagement_count = post['likes']['count'] + post['comments']['count']
                elapsed = (now - post['date']) / 60.  # in min
                is_likable = (engagement_count / elapsed) > self.thresh
                ignoring = any([re.search(r'#\w*{}'.format(t.lower()), post['caption'].lower())
                               for t in self.ignore_tags])
                if (is_photo and is_likable and not ignoring
                        and (self.min_engagements <= engagement_count <= self.max_engagements)):
                    likable_posts.append(post.get('code'))

            k = 0
            while k < len(likable_posts):
                code = likable_posts[k]
                if code not in self.liked_posts:
                    post_url = 'https://www.instagram.com/p/{}'.format(code)
                    self.driver.get(post_url)
                    try:
                        heart = self.driver.find_element_by_xpath('.//span[contains(@class, "coreSpriteHeartOpen")]')
                        heart.click()
                        self.like_count += 1
                        self.liked_posts.append(code)
                        if self.like_count >= self.count_limit:
                            limit_reached = True
                            break
                    except NoSuchElementException:
                        pass
                k += 1

        except NoSuchElementException:
            pass

        finally:
            return limit_reached


def parse_inputs(option, opt, value, parser):
    setattr(parser.values, option.dest, value.split(','))


def main():
    parser = optparse.OptionParser()
    parser.add_option('-U', '--username', dest='username')
    parser.add_option('-N', '--num-loops', dest='num_loops', type='int', default=10,
                      help="Number of loop")
    parser.add_option('-n', '--num-tags', dest='num_tags', type='int',
                      help="Number of hashtags to explore in each loop")
    parser.add_option('-I', '--input', dest='filename', help='Full input file path')
    # parser.add_option('--tag', dest='input', type='string', action='callback',
    #                   callback=parse_inputs, help="Hastag values separated by comma")
    parser.add_option('-r', '--ratio', dest='ratio', type='float', default=4)
    # parser.add_option('-v', '--get-videos', dest='video', action='store_true', default=False)
    parser.add_option('--ignore', dest='ignore', type='string', action='callback',
                      callback=parse_inputs)
    parser.add_option('--top', dest='top', action='store_true', default=False)
    options, remainder = parser.parse_args()

    driver, login_success = load_instagram(options.username)
    if login_success:
        mybot = HeartGiver(
                    driver=driver,
                    tag_data=options.filename,
                    ignore=options.ignore,
                    thresh=options.ratio,
                    get_top_posts=options.top,
                    min_engagements=15,
                    count_limit=55
                )

        while True:
            mybot.run(options.num_loops, options.num_tags)
            ans = raw_input('Quit? [y/n] ')
            while ans.strip().lower() not in ('y', 'n'):
                ans = raw_input('Quit? [y/n] ')
            if ans == 'y':
                driver.quit()
                break

    else:
        driver.quit()


if __name__ == '__main__':
    main()
