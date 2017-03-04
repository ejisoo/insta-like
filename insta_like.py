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
import os
import random
import re
import time

# Like count limit.
# Nobody knows how many times you can like without getting banned..
count_limit = 60


def load_instagram(username = ''):
    """
    Load selenium driver and log into your Instagram account
    """
    driver = webdriver.Chrome()
    driver.set_window_size(800,800)
    driver.set_window_position(600, 0)
    driver.get('https://www.instagram.com/accounts/login')

    if username:
        password = getpass.getpass('Password: ')
        username_field = driver.find_element_by_name('username')
        password_field = driver.find_element_by_name('password')
        actions = ActionChains(driver).click(username_field).send_keys(username).click(password_field).send_keys(password).send_keys(Keys.RETURN)
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


def worker(driver, tags, N = 10, ntag = 10, thresh = 2, sliding_window = 3600.0, top_posts = True,
           window_counter = 1, visit_history = []):
    """
    """
    start_time = time.time()
    like_count, iloop = 0, 0
    # print('App start time: ' + str(start_time))
    while iloop < N:
        # Skip the sleep on the first run (duh)
        if iloop != 0: time.sleep(600.0 - ((time.time() - start_time) % 600.0))
        # print('Starting 10-min loop #{}/{}'.format(*map(str, (iloop + 1, N))))
        random.shuffle(tags)

        # Loop over ntag shuffled tags at a time
        for tag in tags[:ntag]:
            if (time.time() - start_time) > sliding_window * window_counter:
                window_counter += 1  # TO-DO: change this to mod (%)
                like_count = 0  # one-hour window expired, so reset the like_count
            tag_url = 'https://www.instagram.com/explore/tags/%s' % tag
            # print('Current tag: ' + tag)
            driver.get(tag_url)
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CLASS_NAME, '_totu9'))
            )
            like_count, visit_history, flag = like_post_by_tag(driver, tag, thresh, like_count, visit_history, top_posts)
            driver.implicitly_wait(1)

        if flag:
            elapsed = ((time.time() - start_time) % sliding_window)
            # print('WARNING: Rate limit reached. Sleeping for ' + str(sliding_window - elapsed) + ' seconds.')
            time.sleep(sliding_window - elapsed)
        else:
            # print('Like count is ' + str(like_count) + ' in this one-hour sliding window.')
        iloop += 1

    return like_count, visit_history


def like_post_by_tag(driver, tag, thresh, like_count, visit_history, top_posts):
    """
    Like likable photos by hashtag
    Likable photo defined here is the photo with engagements per minute > threshold
    """
    # print('Quality threshold is ' + str(thresh))
    try:
        loadmore_class = ['8imhp', 'oidfu']  # Two possible Load More as of February 2017
        element = next((driver.find_element_by_css_selector('a._%s' % c) for c in loadmore_class))
        element.click()

        # Scroll down just enough for about 20 photos
        for _ in range(5):
            driver.execute_script('window.scrollTo(0, document.body.scrollHeight);')

        now = time.time()
        source = driver.page_source

        photos = []
        json_data = re.search(r'(?s)<script [^>]*>window\._sharedData'
                              r'.*?"nodes".+?</script>', source)
        json_data = re.search(r'{.+}', json_data.group(0))
        json_data = json.loads(json_data.group(0))
        photos = list(gen_dict_extract('nodes', json_data))
        if top_posts:
            photos = photos[1] + photos[0]
        else:
            photos = photos[0]

        likable_photos = []
        for photo in photos:
            # Get photo JSON data
            is_photo = not photo['is_video']
            engagement_count = photo['likes']['count'] + photo['comments']['count']
            elapsed = (now - photo['date']) / 60.  # in min
            is_likable = engagement_count / elapsed > thresh
            if is_photo and is_likable:
                likable_photos.append(photo.get('code'))

        limit_reached, li = False, 0
        while not limit_reached and li <= len(likable_photos)-1:
            code = likable_photos[li]
            if code not in visit_history:
                post_url = 'https://www.instagram.com/p/%s' % code
                driver.get(post_url)
                try:
                    heart = driver.find_element_by_xpath('.//span[@class = "_soakw coreSpriteHeartOpen"]')
                    heart.click()
                    visit_history.append(code)
                    if like_count >= count_limit:
                        limit_reached = True
                except NoSuchElementException:
                    pass
            like_count += 1
            li += 1

    except NoSuchElementException:
        pass

    return like_count, visit_history, limit_reached


def load_tags(filename = ''):
    """
    parse hastag text files
    """
    if filename:
        with open(filename, 'r') as f:
            raw_lines = f.readlines()
        tags_text = ' '.join([l for l in raw_lines if '#' in l])
        rx = re.compile(r'#(\w+)\s*(?:\r|\n)?', re.I)
        return rx.findall(tags_text)
    else:
        # Return 10 popular hastags by default
        return ['cute', 'love', 'lifestyle', 'fun', 'tbt', 'beautiful', 'family', 'food', 'coffee', 'art']


def gen_dict_extract(key, var):
    if hasattr(var, 'iteritems'):
        for k, v in var.iteritems():
            if k == key:
                yield v
            if isinstance(v, dict):
                for result in gen_dict_extract(key, v):
                    yield result
            elif isinstance(v, list):
                for d in v:
                    for result in gen_dict_extract(key, d):
                        yield result


if __name__ == '__main__':

    driver, login_success = load_instagram()
    # tags  = load_tags('hashtags.txt')
    tags  = load_tags()
    if login_success:
        like_count, visit_history = worker(driver = driver, tags = tags, top_posts = False)