#!/usr/bin/python
# -*- coding: utf-8 -*-

import argparse
import codecs
import errno
import json
import logging.config
import os
import re
import sys
import time

import concurrent.futures
import requests
import tqdm

from http import Response
from datetime import datetime

class JinstaScrape(object):
  ######## CONSTANTS ###########################################################
  # URLs
  INSTAGRAM_URL= 'https://www.instagram.com/'
  JSON_QUERY = '?__a=1'
  VIEW_MEDIA_URL = INSTAGRAM_URL + 'p/{0}/' + JSON_QUERY
  QUERY_HASHTAG = INSTAGRAM_URL + 'graphql/query/?query_id=17882293912014529&tag_name={0}&first=100&after={1}'
  QUERY_LOCATION = INSTAGRAM_URL + 'graphql/query/?query_id=17881432870018455&id={0}&first=100&after={1}'
  # VALUES
  IMAGE_TYPENAME = 'GraphImage'
  VIDEO_TYPENAME = 'GraphVideo'
  CAROUSEL_TYPENAME = 'GraphSidecar'
  MAX_RETRIES = 5
  RETRY_COOLDOWN = 6
  MAX_WORKERS = 10

  def __init__(self, **kwargs):
    """
    initializes:
      self.scrape_by_hashtags
      self.hashtags_path
      self.hashtags
      self.download
      self.downloads_directory
      self.session
      self.manifest_path
      self.manifest
    """
    # Load arguments as instance variables
    for key, value in kwargs.iteritems():
      self.__dict__[key] = value

    self.session = requests.Session()
    self.__load_hashtags() # assign self.hashtags
    self.__load_manifest() # assign self.manifest

  def scrape(self):
    """Scraping function"""
    if self.scrape_by_hashtags:
      try:
        self.__scrape_hashtags()
      except KeyboardInterrupt:
        print 'Force exit requested!'
        self.__writeout_manifest() # save current manifest
        print 'Exiting program...\n'

    if self.download:
      try:
        self.__download_scraped_media()
      except KeyboardInterrupt:
        print 'Force exit requested!'
        self.__writeout_manifest() # save current manifest
        print 'Exiting program...\n'

  ######## PRIVATE METHODDS ####################################################
  def __load_manifest(self):
    """Loads json manifest and assign to self.manifest"""
    try:
      with open(self.manifest_path) as f:
        self.manifest = json.load(f) # load previous manifest if exists
    except:
      self.manifest = json.loads("{}") # else use new empty manifest

  def __load_hashtags(self):
    """Loads hashtags and assign to self.hashtags"""
    self.hashtags = []
    if self.scrape_by_hashtags:
      try:
        with open(self.hashtags_path) as f:
          for line in f.readlines():
            tag = line.strip()
            # if not empty and not comment
            if tag and not tag.startswith('#'):
              self.hashtags.append(tag)
      except:
        print 'Please provide a valid text file path for hashtags list'

  def __scrape_hashtags(self):
    """Scrape posts via hashtags and save information to manifest"""
    scrape_start_time = datetime.now()
    # For every hashtag in list
    for tag_name in self.hashtags:
      print 'INITIATED SCRAPING FOR #{0}'.format(tag_name)
      new_scrape_count = 0
      try:
        nodes = JinstaScrape.get_posts_generator('hashtag', tag_name, self.session)
        if nodes: # if not None
          for node in nodes:
            shortcode = node['shortcode']
            if self.__not_already_scraped(shortcode):
              post_node = JinstaScrape.get_post_node(shortcode, self.session)
              if post_node: # if not None
                self.__update_manifest(post_node)
                print 'Post shortcode={0} scraped!'.format(shortcode)
                new_scrape_count += 1
      except Exception as e:
        print 'Exception encountered during scraping: ', e
        self.__writeout_manifest() # save current manifest
        print 'Retrying scrape...'
        self.__scrape_hashtags()
        return
      
      # Upon completion of scraping hashtag with tag_name
      print '{0} new posts collected for #{1}!'.format(new_scrape_count, tag_name)

    # Upon completion of scraping all hashtags
    print 'SCRAPING COMPLETED!'
    print 'Scrape time elapsed: {}s'.format(JinstaScrape.time_elapsed(scrape_start_time))
    
    self.__writeout_manifest() # Save completed manifest

  def __download_scraped_media(self):
    """Downloads all undownloaded media in manifest"""
    # Terminate if manifest is empty
    if not self.manifest:
      print 'Nothing to download! Exiting program...'
      return

    download_start_time = datetime.now()
    future_to_download = {}
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=JinstaScrape.MAX_WORKERS)
    
    # Iterate each scraped post in manifest and add to concurrent download executor
    for shortcode in self.manifest:
      post = self.manifest[shortcode]
      # Iterate each media in post
      for media in post['media_items']:
        # If media not yet downloaded
        if not media['downloaded_path']:
          future = executor.submit(JinstaScrape.download_media, media, self.downloads_directory, shortcode, self.session)
          future_to_download[future] = media
    
    # Download each post in executor's list
    failure_count = 0
    for future in tqdm.tqdm(concurrent.futures.as_completed(future_to_download), total=len(future_to_download), desc='Downloading media'):
      media = future_to_download[future]
      if future.exception() is not None:
        print 'Media shortcode={0} at {1} generated an exception: {2}'.format(media['shortcode'], media['url'], future.exception())
        failure_count += 1

    # Upon completion
    print 'Download time elapsed: {}s'.format(JinstaScrape.time_elapsed(download_start_time))
    if failure_count:
      print failure_count, 'failed downloads'
    
    self.__writeout_manifest() # write out updated manifest

  def __not_already_scraped(self, shortcode):
    """Asserts if post with given shortcode has been scraped"""
    return shortcode not in self.manifest

  def __update_manifest(self, post_node):
    """Update manifest with give post_node"""
    self.manifest[post_node['shortcode']] = JinstaScrape.process_post(post_node)

  def __writeout_manifest(self):
    """Write manifest to disk"""
    print 'Saving manifest to', self.manifest_path
    self.write_json(self.manifest, self.manifest_path)

  ######## PUBLIC STATIC METHODS ###############################################
  @staticmethod
  def get_post_node(shortcode, session):
    """
    Returns media post node of given media shortcode
    Returns None if HTTP request failed
    """
    url = JinstaScrape.VIEW_MEDIA_URL.format(shortcode)
    response = JinstaScrape.request(url, session, 0)
    if response:
      try:
        payload = response.json()
        return payload["graphql"]["shortcode_media"]
      except Exception as e:
        print 'Parsing {0} encountered: {1}'.format(url, e)
        return None
    else:
      return None

  @staticmethod
  def get_posts_generator(query_type, query_value, session):
    """Returns a python generator for the exhaustive posts from a query"""
    end_cursor = ''
    if query_type == 'hashtag':
      getter = JinstaScrape.get_hashtagged_posts
    elif query_type == 'location':
      getter = JinstaScrape.get_location_posts

    while True:
      edges, end_cursor = getter(query_value, end_cursor, session)
      if not edges: # if request failed
        break
      for edge_node in edges:
        yield edge_node['node']
      if not end_cursor: # end if no more pages left in query
        break

  @staticmethod
  def get_hashtagged_posts(hashtag, end_cursor, session):
    """
    Gets the list of hashtagged posts nodes and edges, end_cursor
    returns None, None if HTTP request failed
    """
    url = JinstaScrape.QUERY_HASHTAG.format(hashtag, end_cursor)
    response = JinstaScrape.request(url, session, 0)
    if response:
      try:
        payload = response.json()
        hashtag_result = payload['data']['hashtag']['edge_hashtag_to_media']
        # return edges, end_cursor
        edges = hashtag_result['edges']
        end_cursor = hashtag_result['page_info']['end_cursor']
        return edges, end_cursor 
      except Exception as e:
        print 'Parsing {0} encountered: {1}'.format(url, e)
        return None, None
    else:
      return None, None

  @staticmethod
  def request(url, session, retry_count):
    """
    Post get request to given url with exponential backoff retry scheme
    returns response object on success, else None
    """
    print 'Requesting', url
    response = session.get(url)
    if Response(response.status_code).is_success:
      return response
    else:
      print 'HTTP {0} for {1}'.format(str(response.status_code), url)
      if retry_count < JinstaScrape.MAX_RETRIES:
        # Determine suitable timeout
        timeout = 2 ** (6 + retry_count) # use exponential backoff (start at 64s)
        if 'Retry-After' in response.headers:
          timeout = int(response.headers['Retry-After'])
        print 'Retrying in {0}s'.format(timeout)
        # Timeout
        time.sleep(timeout)
        # Retry
        return JinstaScrape.request(url, session, retry_count + 1)
      else:
        print 'Max retries exceeded. Aborting current query.'
        return None

  @staticmethod
  def get_location_posts():
    # TODO
    return

  @staticmethod
  def write_file(data, file_path):
    """Writes data to given file_path"""
    with open(file_path, 'wb') as f:
      f.write(data)

  @staticmethod
  def write_json(data, file_path):
    """Writes json data to given file_path"""
    with open(file_path, 'wb') as f:
      json.dump(data, codecs.getwriter('utf-8')(f), indent=2, ensure_ascii=False)
  
  @staticmethod
  def process_post(post_node):
    """Processes and formats scraped post node into desired format"""
    processed_post = {
      '__typename': post_node['__typename'],
      'id': post_node['id'],
      'shortcode': post_node['shortcode'],
      'is_video': post_node['is_video'],
      'taken_at_timestamp': post_node['taken_at_timestamp'],
      'last_scraped_at': str(datetime.now()),
      'is_ad': post_node['is_ad'],
      'location': post_node['location'],
      'owner': {
        'id': post_node['owner']['id'],
        'profile_pic_url': post_node['owner']['profile_pic_url'],
        'username': post_node['owner']['username'],
        'full_name': post_node['owner']['full_name'],
        'is_private': post_node['owner']['is_private'],
        'is_unpublished': post_node['owner']['is_unpublished'],
        'is_verified': post_node['owner']['is_verified']
      }
    }

    # process media
    processed_post['media_items'] = JinstaScrape.process_media(post_node)

    # process caption
    processed_post["caption"] = JinstaScrape.process_caption(post_node)

    # process tags
    processed_post["tags"] = JinstaScrape.process_tags(processed_post)
    
    # process comments
    processed_post["comments"] = JinstaScrape.process_comments(post_node)

    # process likes
    processed_post['likes'] = JinstaScrape.process_likes(post_node)
    
    return processed_post

  @staticmethod
  def process_media(post_node):
    """Process media in post and returns as a list (multiple items for carousel types)"""
    media_items = []
    JinstaScrape.populate_media_items(media_items, post_node)
    return media_items

  @staticmethod
  def process_caption(post_node):
    """Process user post caption in post and returns formatted caption"""
    processed_caption = {
      'text': ''
    }
    if 'edge_media_to_caption' in post_node and post_node['edge_media_to_caption'] and post_node['edge_media_to_caption']['edges']:
      processed_caption['text'] = post_node['edge_media_to_caption']['edges'][0]['node']['text']
      processed_caption['caption_is_edited'] = post_node['caption_is_edited']
    return processed_caption

  @staticmethod
  def process_tags(processed_post):
    """
    Process hashtags in post caption and returns them as a list
    NOTE: must take in a post after processing captions
    """
    return JinstaScrape.extract_tags(processed_post['caption']['text'])

  @staticmethod
  def process_comments(post_node):
    """Process the preview comments (if any) on post page and returns formatted comments"""
    comments_node = post_node['edge_media_to_comment']
    processed_comments = {
      'count': comments_node['count'],
      'has_next_page': comments_node['page_info']['has_next_page'],
      'end_cursor': comments_node['page_info']['end_cursor'],
      'comments_disabled': post_node['comments_disabled']
    }
    entries = []
    # if there are comments
    comments_edges = comments_node['edges']
    if len(comments_edges):
      for edge in comments_edges:
        entries.append(edge['node'])
    processed_comments['entries'] = entries
    return processed_comments

  @staticmethod
  def process_likes(post_node):
    """Process the preview likes (if any) on post page and returns processed likes"""
    likes_node = post_node['edge_media_preview_like']
    processed_likes = {
      'count': likes_node['count']
    }
    entries = []
    likes_edges = likes_node['edges']
    # if there are likes
    if len(likes_edges):
      for edge in likes_edges:
        entries.append(edge['node'])
    processed_likes['entries'] = entries
    return processed_likes

  @staticmethod
  def populate_media_items(media_items, media_node):
    """
    Formats all media (recursive for carousel) and adds them to media_items
    Recursion guaranteed termination because carousel does not nest. i.e. no carousel within carousel
    """
    # Carousel
    if JinstaScrape.is_carousel(media_node):
      # Iterate each carousel item
      for carousel_media_edge in media_node['edge_sidecar_to_children']['edges']:
        JinstaScrape.populate_media_items(media_items, carousel_media_edge['node']) # recurse
    
    # Image or Video (base case)
    else:
      processed_media = {
        '__typename': media_node['__typename'],
        'shortcode': media_node['shortcode'],
        'id': media_node['id'],
        'downloaded_path': '' # will be assigned the downloaded path of media
      }

      # Image
      if JinstaScrape.is_image(media_node):
        processed_media['url'] = JinstaScrape.get_original_image(media_node['display_url'])
      # Video
      elif JinstaScrape.is_video(media_node):
        processed_media['url'] = media_node['video_url']
      
      # Process user tags
      tagged_users = []
      tagged_users_edges = media_node['edge_media_to_tagged_user']['edges']
      if len(tagged_users_edges):
        for edge in tagged_users_edges:
          tagged_users.append(edge['node'])
      processed_media['tagged_users'] = tagged_users

      # Append to media_items
      media_items.append(processed_media)

  @staticmethod
  def is_image(media_node):
    """Asserts if media node is image type"""
    return media_node['__typename'] == JinstaScrape.IMAGE_TYPENAME

  @staticmethod
  def is_video(media_node):
    """Asserts if media node is video type"""
    return media_node['__typename'] == JinstaScrape.VIDEO_TYPENAME

  @staticmethod
  def is_carousel(media_node):
    """Asserts if media node is carousel type"""
    return media_node['__typename'] == JinstaScrape.CAROUSEL_TYPENAME

  @staticmethod
  def get_original_image(url):
    """Gets the full-size image from the specified url"""
    # remove dimensions to get largest image
    url = re.sub(r'/[sp]\d{3,}x\d{3,}/', '/', url)
    # get non-square image if one exists
    url = re.sub(r'/c\d{1,}.\d{1,}.\d{1,}.\d{1,}/', '/', url)
    return url

  @staticmethod
  def extract_tags(text):
    """Extracts the hashtags from given text"""    
    tags = []
    # include words and emojis
    tags = re.findall(
      r"(?<!&)#(\w+|(?:[\xA9\xAE\u203C\u2049\u2122\u2139\u2194-\u2199\u21A9\u21AA\u231A\u231B\u2328\u2388\u23CF\u23E9-\u23F3\u23F8-\u23FA\u24C2\u25AA\u25AB\u25B6\u25C0\u25FB-\u25FE\u2600-\u2604\u260E\u2611\u2614\u2615\u2618\u261D\u2620\u2622\u2623\u2626\u262A\u262E\u262F\u2638-\u263A\u2648-\u2653\u2660\u2663\u2665\u2666\u2668\u267B\u267F\u2692-\u2694\u2696\u2697\u2699\u269B\u269C\u26A0\u26A1\u26AA\u26AB\u26B0\u26B1\u26BD\u26BE\u26C4\u26C5\u26C8\u26CE\u26CF\u26D1\u26D3\u26D4\u26E9\u26EA\u26F0-\u26F5\u26F7-\u26FA\u26FD\u2702\u2705\u2708-\u270D\u270F\u2712\u2714\u2716\u271D\u2721\u2728\u2733\u2734\u2744\u2747\u274C\u274E\u2753-\u2755\u2757\u2763\u2764\u2795-\u2797\u27A1\u27B0\u27BF\u2934\u2935\u2B05-\u2B07\u2B1B\u2B1C\u2B50\u2B55\u3030\u303D\u3297\u3299]|\uD83C[\uDC04\uDCCF\uDD70\uDD71\uDD7E\uDD7F\uDD8E\uDD91-\uDD9A\uDE01\uDE02\uDE1A\uDE2F\uDE32-\uDE3A\uDE50\uDE51\uDF00-\uDF21\uDF24-\uDF93\uDF96\uDF97\uDF99-\uDF9B\uDF9E-\uDFF0\uDFF3-\uDFF5\uDFF7-\uDFFF]|\uD83D[\uDC00-\uDCFD\uDCFF-\uDD3D\uDD49-\uDD4E\uDD50-\uDD67\uDD6F\uDD70\uDD73-\uDD79\uDD87\uDD8A-\uDD8D\uDD90\uDD95\uDD96\uDDA5\uDDA8\uDDB1\uDDB2\uDDBC\uDDC2-\uDDC4\uDDD1-\uDDD3\uDDDC-\uDDDE\uDDE1\uDDE3\uDDEF\uDDF3\uDDFA-\uDE4F\uDE80-\uDEC5\uDECB-\uDED0\uDEE0-\uDEE5\uDEE9\uDEEB\uDEEC\uDEF0\uDEF3]|\uD83E[\uDD10-\uDD18\uDD80-\uDD84\uDDC0]|(?:0\u20E3|1\u20E3|2\u20E3|3\u20E3|4\u20E3|5\u20E3|6\u20E3|7\u20E3|8\u20E3|9\u20E3|#\u20E3|\\*\u20E3|\uD83C(?:\uDDE6\uD83C(?:\uDDEB|\uDDFD|\uDDF1|\uDDF8|\uDDE9|\uDDF4|\uDDEE|\uDDF6|\uDDEC|\uDDF7|\uDDF2|\uDDFC|\uDDE8|\uDDFA|\uDDF9|\uDDFF|\uDDEA)|\uDDE7\uD83C(?:\uDDF8|\uDDED|\uDDE9|\uDDE7|\uDDFE|\uDDEA|\uDDFF|\uDDEF|\uDDF2|\uDDF9|\uDDF4|\uDDE6|\uDDFC|\uDDFB|\uDDF7|\uDDF3|\uDDEC|\uDDEB|\uDDEE|\uDDF6|\uDDF1)|\uDDE8\uD83C(?:\uDDF2|\uDDE6|\uDDFB|\uDDEB|\uDDF1|\uDDF3|\uDDFD|\uDDF5|\uDDE8|\uDDF4|\uDDEC|\uDDE9|\uDDF0|\uDDF7|\uDDEE|\uDDFA|\uDDFC|\uDDFE|\uDDFF|\uDDED)|\uDDE9\uD83C(?:\uDDFF|\uDDF0|\uDDEC|\uDDEF|\uDDF2|\uDDF4|\uDDEA)|\uDDEA\uD83C(?:\uDDE6|\uDDE8|\uDDEC|\uDDF7|\uDDEA|\uDDF9|\uDDFA|\uDDF8|\uDDED)|\uDDEB\uD83C(?:\uDDF0|\uDDF4|\uDDEF|\uDDEE|\uDDF7|\uDDF2)|\uDDEC\uD83C(?:\uDDF6|\uDDEB|\uDDE6|\uDDF2|\uDDEA|\uDDED|\uDDEE|\uDDF7|\uDDF1|\uDDE9|\uDDF5|\uDDFA|\uDDF9|\uDDEC|\uDDF3|\uDDFC|\uDDFE|\uDDF8|\uDDE7)|\uDDED\uD83C(?:\uDDF7|\uDDF9|\uDDF2|\uDDF3|\uDDF0|\uDDFA)|\uDDEE\uD83C(?:\uDDF4|\uDDE8|\uDDF8|\uDDF3|\uDDE9|\uDDF7|\uDDF6|\uDDEA|\uDDF2|\uDDF1|\uDDF9)|\uDDEF\uD83C(?:\uDDF2|\uDDF5|\uDDEA|\uDDF4)|\uDDF0\uD83C(?:\uDDED|\uDDFE|\uDDF2|\uDDFF|\uDDEA|\uDDEE|\uDDFC|\uDDEC|\uDDF5|\uDDF7|\uDDF3)|\uDDF1\uD83C(?:\uDDE6|\uDDFB|\uDDE7|\uDDF8|\uDDF7|\uDDFE|\uDDEE|\uDDF9|\uDDFA|\uDDF0|\uDDE8)|\uDDF2\uD83C(?:\uDDF4|\uDDF0|\uDDEC|\uDDFC|\uDDFE|\uDDFB|\uDDF1|\uDDF9|\uDDED|\uDDF6|\uDDF7|\uDDFA|\uDDFD|\uDDE9|\uDDE8|\uDDF3|\uDDEA|\uDDF8|\uDDE6|\uDDFF|\uDDF2|\uDDF5|\uDDEB)|\uDDF3\uD83C(?:\uDDE6|\uDDF7|\uDDF5|\uDDF1|\uDDE8|\uDDFF|\uDDEE|\uDDEA|\uDDEC|\uDDFA|\uDDEB|\uDDF4)|\uDDF4\uD83C\uDDF2|\uDDF5\uD83C(?:\uDDEB|\uDDF0|\uDDFC|\uDDF8|\uDDE6|\uDDEC|\uDDFE|\uDDEA|\uDDED|\uDDF3|\uDDF1|\uDDF9|\uDDF7|\uDDF2)|\uDDF6\uD83C\uDDE6|\uDDF7\uD83C(?:\uDDEA|\uDDF4|\uDDFA|\uDDFC|\uDDF8)|\uDDF8\uD83C(?:\uDDFB|\uDDF2|\uDDF9|\uDDE6|\uDDF3|\uDDE8|\uDDF1|\uDDEC|\uDDFD|\uDDF0|\uDDEE|\uDDE7|\uDDF4|\uDDF8|\uDDED|\uDDE9|\uDDF7|\uDDEF|\uDDFF|\uDDEA|\uDDFE)|\uDDF9\uD83C(?:\uDDE9|\uDDEB|\uDDFC|\uDDEF|\uDDFF|\uDDED|\uDDF1|\uDDEC|\uDDF0|\uDDF4|\uDDF9|\uDDE6|\uDDF3|\uDDF7|\uDDF2|\uDDE8|\uDDFB)|\uDDFA\uD83C(?:\uDDEC|\uDDE6|\uDDF8|\uDDFE|\uDDF2|\uDDFF)|\uDDFB\uD83C(?:\uDDEC|\uDDE8|\uDDEE|\uDDFA|\uDDE6|\uDDEA|\uDDF3)|\uDDFC\uD83C(?:\uDDF8|\uDDEB)|\uDDFD\uD83C\uDDF0|\uDDFE\uD83C(?:\uDDF9|\uDDEA)|\uDDFF\uD83C(?:\uDDE6|\uDDF2|\uDDFC))))[\ufe00-\ufe0f\u200d]?)+",
      text, re.UNICODE)
    tags = list(set(tags))

    return tags

  @staticmethod
  def download_media(media, downloads_directory, post_shortcode, session):
    """Downloads the media to directory"""
    JinstaScrape.make_directory(downloads_directory)
    url = media['url']
    file_name = post_shortcode + '.' + url.split('/')[-1].split('?')[0]
    file_path = os.path.join(downloads_directory, file_name)
    is_video = True if 'mp4' in file_name else False

    if not os.path.isfile(file_path):
      with open(file_path, 'wb') as media_file:
        try:
          # Video
          if is_video:
            r = session.get(url, stream=True)
            for chunk in r.iter_content(chunk_size=1024):
              if chunk:
                media_file.write(chunk)
          # Image
          else:
            content = session.get(url).content
            media_file.write(content)
          
          # Update media for successful download
          media['downloaded_path'] = file_path
          media['downloaded_at'] = str(datetime.now())
        except requests.exceptions.ConnectionError:
          time.sleep(JinstaScrape.RETRY_COOLDOWN)
          # Video
          if is_video:
            r = session.get(url, stream=True)
            for chunk in r.iter_content(chunk_size=1024):
              if chunk:
                media_file.write(chunk)
          # Image
          else:
            content = session.get(url).content
            media_file.write(content)

  @staticmethod
  def make_directory(directory):
    """Creates a directory."""
    try:
      os.makedirs(directory)
    except OSError as err:
      if err.errno == errno.EEXIST and os.path.isdir(directory):
        # Directory already exists
        pass
      else:
        # Target dir exists as a file, or a different error
        raise

  @staticmethod
  def time_elapsed(start_datetime):
    """Returns formatted string representing time elapsed from start time to now"""
    d = datetime.now() - start_datetime # datetime timedelta
    return "%s days, %.2dh: %.2dm: %.2ds" % (d.days,d.seconds//3600,(d.seconds//60)%60, d.seconds%60)

def main():
  parser = argparse.ArgumentParser(
    description="Scrapes Instagram posts by hashtags and locations",
    formatter_class=argparse.RawDescriptionHelpFormatter
  )
  parser.add_argument('--scrape-by-hashtags', '-sbh', default=True, help='Indicates if scraping by hashtags')
  parser.add_argument('--hashtags-path', '-hp', default='./hashtags.txt', help='Path for text file containing list of hashtags to scrape')
  parser.add_argument('--manifest-path', '-mp', default='./manifest.json', help='Path for JSON manifest file')
  parser.add_argument('--download', '-d', default=False, help='Download the images and videos')
  parser.add_argument('--downloads-directory', '-dd', default='./downloads', help='Downloads directory')
  
  args = parser.parse_args()
  scraper = JinstaScrape(**vars(args))
  scraper.scrape()

if __name__ == '__main__':
  main()