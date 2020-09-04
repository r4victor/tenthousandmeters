#!/usr/bin/env python
# -*- coding: utf-8 -*- #

# General

AUTHOR = 'Victor Skvortsov'
SITENAME = 'Ten thousand meters'
SITESUBTITLE = 'Diving deep, flying high to see why'
SITEURL = ''

TIMEZONE = 'Europe/London'

DEFAULT_LANG = 'en'

# Feed generation is usually not desired when developing
FEED_ALL_ATOM = None
CATEGORY_FEED_ATOM = None
TRANSLATION_FEED_ATOM = None
AUTHOR_FEED_ATOM = None
AUTHOR_FEED_RSS = None

# Social widget
# SOCIAL = (('GitHub', 'https://github.com/r4victor'),)

GOOGLE_ANALYTICS = 'UA-65327549-5'

PATH = 'content'

DELETE_OUTPUT_DIRECTORY = True

# View

DEFAULT_PAGINATION = False

DISPLAY_CATEGORIES_ON_MENU = False
DISPLAY_PAGES_ON_MENU = False

MENUITEMS = [
    ('about', '/about/'),
    ('blog', '/'),
    ('materials', '/materials/'),
]

THEME = 'themes/notmyidea/'

# Paths & URLs

AUTHORS_SAVE_AS = ''
CATEGORIES_SAVE_AS = ''

ARTICLE_SAVE_AS = 'blog/{slug}.html'
ARTICLE_URL = 'blog/{slug}/'

AUTHOR_SAVE_AS = ''

CATEGORY_SAVE_AS = ''

DRAFT_SAVE_AS = 'drafts/{slug}.html'
DRAFT_URL = 'drafts/{slug}/'

PAGE_PATHS = ('pages', 'materials')
PAGE_SAVE_AS = '{slug}.html'
PAGE_URL = '{slug}/'

TAG_SAVE_AS = 'tag/{slug}.html'
TAG_URL = 'tag/{slug}/'

# Custom

SITETITLE = 'TenThousandMeters.com'