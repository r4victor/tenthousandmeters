#!/usr/bin/env python
# -*- coding: utf-8 -*- #

import os

# General

AUTHOR = 'Victor Skvortsov'
SITENAME = 'Ten thousand meters'
SITESUBTITLE = 'Diving deep, flying high to see why'
SITEURL = os.getenv('SITEURL', '')

TIMEZONE = 'UTC'

DEFAULT_LANG = 'en'

# Feed generation is usually not desired when developing
FEED_DOMAIN = SITEURL
FEED_ATOM = 'feeds/atom.xml'
FEED_ALL_ATOM = 'feeds/all.atom.xml'
TAG_FEED_ATOM = 'tag/{slug}/feeds/atom.xml'
TAG_FEED_ATOM_URL = 'tag/{slug}/feeds/atom.xml'
CATEGORY_FEED_ATOM = None
TRANSLATION_FEED_ATOM = None
AUTHOR_FEED_ATOM = None
AUTHOR_FEED_RSS = None

# Social widget
SOCIAL_WIDGET_NAME = 'follow'
# SOCIAL = (('GitHub', 'https://github.com/r4victor'),)

GOOGLE_ANALYTICS = 'G-DBXG66RFRF'

PATH = 'content'

DELETE_OUTPUT_DIRECTORY = False

PLUGINS = ['pelican.plugins.render_math']

# View

DEFAULT_PAGINATION = False

DISPLAY_CATEGORIES_ON_MENU = False
DISPLAY_PAGES_ON_MENU = False

MENUITEMS = [
    ('about', '/about/'),
    ('blog', '/'),
    ('links', '/links/page-1/'),
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

OUTPUT_PATH = '../output/'

PAGE_PATHS = ('pages', 'materials', 'links')
PAGE_SAVE_AS = '{slug}.html'
PAGE_URL = '{slug}/'

TAG_SAVE_AS = 'tag/{slug}.html'
TAG_URL = 'tag/{slug}/'

# Custom

SITETITLE = 'TenThousandMeters.com'