#!/usr/bin/env python
# coding: utf-8
from __future__ import print_function
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
import getpass
import json
import optparse
import os
import random
import re
import requests
import time

# Like count limit.
# Nobody knows how many times you can like without getting banned..
count_limit = 60


def load_instagram(username = None):
    """
    Load selenium driver and log into your Instagram account
    """
    driver = webdriver.Chrome()
    driver.set_window_size(400,400)
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
                        (By.XPATH, './/a[@class = "_soakw _vbtk2 coreSpriteDesktopNavProfile"]'))
                    )
        return driver, True

    except TimeoutException:
        driver.quit()
        return _, False


def worker(driver, tags, num_loops, num_tags, thresh, get_top_posts,
           sliding_window = 3600.0, window_counter = 1, liked_posts = []):
    """
    Worker explores tags every 10 minutes
    """
    start_time = time.time()
    like_count, i = 0, 0

    while i < num_loops:
        if i != 0: time.sleep(600.0 - ((time.time() - start_time) % 600.0))
        print('Starting 10-min loop #{}/{}'.format(*map(str, (i + 1, num_loops))))
        random.shuffle(tags)

        for ti, tag in enumerate(tags[:num_tags], 1):
            if (time.time() - start_time) > sliding_window * window_counter:
                window_counter += 1  # TO-DO: change this to mod (%)
                like_count = 0  # one-hour window expired, so reset the like_count

            print("==> Now exploring {}/{} tag: #{}".format(ti, num_tags, tag))
            driver.get("https://www.instagram.com/explore/tags/{}".format(tag))
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CLASS_NAME, '_totu9'))
            )

            like_count, liked_posts, flag = like_post_by_tag(driver, tag, thresh, like_count, get_top_posts, liked_posts)

        if flag:
            elapsed = ((time.time() - start_time) % sliding_window)
            print("WARNING: Rate limit reached. Sleeping for {} seconds.".format(str(sliding_window - elapsed)))
            time.sleep(sliding_window - elapsed)
        else:
            print("Like count is {} in this one-hour sliding window.".format(str(like_count)))

        i += 1

    return like_count, liked_posts


def like_post_by_tag(driver, tag, thresh, like_count, get_top_posts, liked_posts):
    """
    Like likable posts by hashtag
    Likable post defined here is the post with engagements per minute > threshold ratio
    """
    try:
        loadmore_class = ['8imhp', 'oidfu']  # Two possible Load More as of February 2017
        element = next((driver.find_element_by_css_selector('a._{}'.format(c)) for c in loadmore_class))
        element.click()
        # Scroll down just enough for about 20 posts
        for _ in range(5):
            driver.execute_script('window.scrollTo(0, document.body.scrollHeight);')

        posts = []
        likable_posts = []

        source = requests.get('http://www.instagram.com/explore/tags/{}'.format(tag)).content
        json_data = json.loads(re.findall(r'<script type="text\/javascript">window._sharedData = (.*?);<\/script>', source)[0])
        now = time.time()

        media_data = json_data['entry_data']['TagPage'][0]['tag']
        top_media = media_data['top_posts']['nodes']
        recent_media = media_data['media']['nodes']

        for post in (top_media + recent_media if get_top_posts else recent_media):
            # Get post JSON data
            is_photo = not post['is_video']
            engagement_count = post['likes']['count'] + post['comments']['count']
            elapsed = (now - post['date']) / 60.  # in min
            is_likable = engagement_count / elapsed > thresh
            if is_photo and is_likable and engagement_count > 10:
                likable_posts.append(post.get('code'))

        limit_reached, li = False, 0
        while not limit_reached and li <= len(likable_posts)-1:
            code = likable_posts[li]
            if code not in liked_posts:
                post_url = 'https://www.instagram.com/p/%s' % code
                driver.get(post_url)
                try:
                    heart = driver.find_element_by_xpath('.//span[@class = "_soakw coreSpriteHeartOpen"]')
                    heart.click()
                    like_count += 1
                    liked_posts.append(code)
                    if like_count >= count_limit:
                        limit_reached = True
                except NoSuchElementException:
                    pass
            li += 1

    except NoSuchElementException:
        pass

    finally:
        return like_count, liked_posts, limit_reached


def load_tags(filename = None):
    """
    Parse textfile that contains hashtags and return list of tags
    """
    if filename is not None:
        with open(filename, 'r') as f:
            raw_lines = f.readlines()
        tags_text = ' '.join([l for l in raw_lines if '#' in l])
        rx = re.compile(r'#(\w+)\s*(?:\r|\n)?', re.I)
        return rx.findall(tags_text)
    else:
        # Return 10 popular tags by default
        return ['cute', 'love', 'lifestyle', 'fun', 'tbt', 'beautiful', 'family', 'food', 'coffee', 'art']


def parse_inputs(option, opt, value, parser):
    setattr(parser.values, option.dest, value.split(','))


def main():
    parser = optparse.OptionParser()
    parser.add_option('-U', '--username', dest='username')
    parser.add_option('-n', '--num-tags', dest='num_tags', type='int',
                      help="Number of hashtags to explore in each loop")
    parser.add_option('-N', '--num-loops', dest='num_loops', type='int', help="Number of loop")
    parser.add_option('-I', '--input', dest='filename', help='Full input file path')
    # parser.add_option('--tag', dest='input', type='string', action='callback',
    #                   callback=parse_inputs, help="Hastag values separated by comma")
    parser.add_option('-r', '--ratio', dest='ratio', type='float')
    # parser.add_option('-v', '--get-videos', dest='video', action='store_true', default=False)
    parser.add_option('--top', dest='top', action='store_true', default=False)
    options, remainder = parser.parse_args()

    tags = load_tags(options.filename)
    driver, login_success = load_instagram(options.username)
    if login_success:
        like_count, liked_posts = worker(
            driver = driver, tags = tags,
            num_loops = options.num_loops if options.num_loops else 10,
            num_tags = options.num_tags,
            thresh = options.ratio if options.ratio else 4,
            get_top_posts = options.top
        )

    driver.quit()


if __name__ == '__main__':
    main()