#!/usr/bin/python
# -*- coding: utf-8 -*-

import argparse
import json
import codecs
import tqdm

from collections import Counter
from datetime import datetime

class Analyzer(object):
  def __init__(self, **kwargs):
    """
    initializes:
      self.manifest_path
      self.output_path
      self.manifest
    """
    # Load arguments as instance variables
    for key, value in kwargs.iteritems():
      self.__dict__[key] = value

    self.__load_manifest()

  def analyze(self):
    if self.manifest:
      hashtags_counter = Counter()
      locations_counter = Counter()
      
      for shortcode, post in tqdm.tqdm(self.manifest.iteritems(), total=len(self.manifest), desc='Analyzing manifest'):
        # filter
        if post['is_ad']:
          continue

        hashtags_counter.update([tag.lower() for tag in post['tags']])
        if post['location']:
          pair = (post['location']['id'], post['location']['name'])
          locations_counter.update([pair])
      
      self.__write_output(hashtags_counter, locations_counter)
      print 'Analysis complete! Output written to', self.output_path
    else:
      print 'No analytics to be done. Program will now exit'

  ######## PRIVATE METHODDS ####################################################
  def __load_manifest(self):
    """Loads json manifest and assign to self.manifest"""
    try:
      with open(self.manifest_path) as f:
        self.manifest = json.load(f) # load previous manifest if exists
    except:
      print 'Manifest not found'
      self.manifest = json.loads("{}") # else use empty manifest

  def __write_output(self, hashtags_counter, locations_counter):
    with open(self.output_path, 'w') as o:
      o.write('#################### ANALYZED ON {0} ####################\n'.format(str(datetime.now())))
      o.write('{0} posts analyzed\n'.format(len(self.manifest)))
      if hashtags_counter:
        o.write('\n-------------------------- HASHTAGS --------------------------\n')
        o.write('{0} unique hashtags:\n'.format(len(hashtags_counter)))
        for tag, count in hashtags_counter.most_common():
          o.write('#{0} : {1}\n'.format(tag.encode('utf-8'), count))
      if locations_counter:
        o.write('\n-------------------------- LOCATIONS --------------------------\n')
        o.write('{0} unique locations:\n'.format(len(locations_counter)))
        for location, count in locations_counter.most_common():
          o.write('{0}, {1} : {2}\n'.format(location[0], location[1].encode('utf-8'), count))

def main():
  parser = argparse.ArgumentParser(
    description="Analyzes scraped posts information from the manifest",
    formatter_class=argparse.RawDescriptionHelpFormatter
  )
  parser.add_argument('--manifest-path', '-mp', default='./manifest.json', help='Path for JSON manifest file')
  parser.add_argument('--output-path', '-o', default='./output.txt', help='Path for analyzed output to be written to')

  args = parser.parse_args()
  analyzer = Analyzer(**vars(args))
  analyzer.analyze()

if __name__ == '__main__':
  main()