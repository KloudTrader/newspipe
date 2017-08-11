import pytz
import logging
from datetime import datetime
from collections import OrderedDict

from flask import current_app, render_template, make_response, \
        request, flash, url_for, redirect
from flask_login import login_required, current_user
from flask_babel import gettext, get_locale
from babel.dates import format_datetime, format_timedelta

import conf
from lib.utils import redirect_url
from lib import misc_utils
from web.models import User, Feed, Article, Role
from web.lib.view_utils import etag_match
from web.views.common import jsonify

from web.controllers import FeedController, \
                            ArticleController, CategoryController

localize = pytz.utc.localize
logger = logging.getLogger(__name__)



@current_app.route('/')
@login_required
def home():
    "Home page for connected users. Displays by default unread articles."
    return render_home()

def render_home(filters=None, head_titles=None,
                page_to_render='home', **kwargs):
    if filters is None:
        filters = {}
    if head_titles is None:
        head_titles = []
    feed_contr = FeedController(current_user.id)
    arti_contr = ArticleController(current_user.id)
    feeds = {feed.id: feed.title for feed in feed_contr.read()}

    in_error = {feed.id: feed.error_count for feed in
                feed_contr.read(error_count__gt=2)}

    filter_ = request.args.get('filter_',
                               'unread' if page_to_render == 'home' else 'all')
    sort_ = request.args.get('sort_', 'date')
    feed_id = int(request.args.get('feed_id', 0))
    limit = request.args.get('limit', 1000)

    if filter_ != 'all':
        filters['readed'] = filter_ == 'read'
    if feed_id:
        filters['feed_id'] = feed_id
        head_titles.append(feed_contr.get(id=feed_id).title)

    sort_param = {"feed": Feed.title.desc(),
                  "date": Article.date.desc(),
                  "article": Article.title.desc(),
                  "-feed": Feed.title.asc(),
                  "-date": Article.date.asc(),
                  "-article": Article.title.asc()
                  }.get(sort_, Article.date.desc())

    articles = arti_contr.read(**filters).join(Article.source). \
                                            order_by(sort_param)
    if limit != 'all':
        limit = int(limit)
        articles = articles.limit(limit)

    def gen_url(filter_=filter_, sort_=sort_, limit=limit, feed_id=feed_id,
                **kwargs):
        o_kwargs = OrderedDict()
        for key in sorted(kwargs):
            o_kwargs[key] = kwargs[key]
        if page_to_render == 'search':
            o_kwargs['query'] = request.args.get('query', '')
            o_kwargs['search_title'] = request.args.get('search_title', 'off')
            o_kwargs['search_content'] = request.args.get(
                    'search_content', 'off')
            # if nor title and content are selected, selecting title
            if o_kwargs['search_title'] == o_kwargs['search_content'] == 'off':
                o_kwargs['search_title'] = 'on'
        o_kwargs['filter_'] = filter_
        o_kwargs['sort_'] = sort_
        o_kwargs['limit'] = limit
        o_kwargs['feed_id'] = feed_id
        return url_for(page_to_render, **o_kwargs)

    articles = list(articles)
    if (page_to_render == 'home' and feed_id or page_to_render == 'search') \
            and filter_ != 'all' and not articles:
        return redirect(gen_url(filter_='all'))

    response = make_response(render_template('home.html', gen_url=gen_url,
                             feed_id=feed_id, page_to_render=page_to_render,
                             filter_=filter_, limit=limit, feeds=feeds,
                             unread=arti_contr.count_by_feed(readed=False),
                             articles=articles, in_error=in_error,
                             head_titles=head_titles, sort_=sort_, **kwargs))
    return response


def _get_filters(in_dict):
    filters = {}
    query = in_dict.get('query')
    if query:
        search_title = in_dict.get('search_title') == 'true'
        search_content = in_dict.get('search_content') == 'true'
        if search_title:
            filters['title__ilike'] = "%%%s%%" % query
        if search_content:
            filters['content__ilike'] = "%%%s%%" % query
        if len(filters) == 0:
            filters['title__ilike'] = "%%%s%%" % query
        if len(filters) > 1:
            filters = {"__or__": filters}
    if in_dict.get('filter') == 'unread':
        filters['readed'] = False
    elif in_dict.get('filter') == 'liked':
        filters['like'] = True
    filter_type = in_dict.get('filter_type')
    if filter_type in {'feed_id', 'category_id'} and in_dict.get('filter_id'):
        filters[filter_type] = int(in_dict['filter_id']) or None
    return filters


@jsonify
def _articles_to_json(articles, fd_hash=None):
    now, locale = datetime.now(), get_locale()
    fd_hash = {feed.id: {'title': feed.title,
                         'icon_url': url_for('icon.icon', url=feed.icon_url)
                                     if feed.icon_url else None}
               for feed in FeedController(current_user.id).read()}

    return {'articles': [{'title': art.title, 'liked': art.like,
            'read': art.readed, 'article_id': art.id, 'selected': False,
            'feed_id': art.feed_id, 'category_id': art.category_id or 0,
            'feed_title': fd_hash[art.feed_id]['title'] if fd_hash else None,
            'icon_url': fd_hash[art.feed_id]['icon_url'] if fd_hash else None,
            'date': format_datetime(localize(art.date), locale=locale),
            'rel_date': format_timedelta(art.date - now,
                    threshold=1.1, add_direction=True,
                    locale=locale)}
            for art in articles.limit(1000)]}


@current_app.route('/getart/<int:article_id>')
@current_app.route('/getart/<int:article_id>/<parse>')
@login_required
@etag_match
@jsonify
def get_article(article_id, parse=False):
    locale = get_locale()
    contr = ArticleController(current_user.id)
    article = contr.get(id=article_id)
    if not article.readed:
        article['readed'] = True
        contr.update({'id': article_id}, {'readed': True})
    article['category_id'] = article.category_id or 0
    feed = FeedController(current_user.id).get(id=article.feed_id)
    article['icon_url'] = url_for('icon.icon', url=feed.icon_url) \
            if feed.icon_url else None
    article['date'] = format_datetime(localize(article.date), locale=locale)
    return article


@current_app.route('/mark_all_as_read', methods=['PUT'])
@login_required
def mark_all_as_read():
    filters = _get_filters(request.json)
    acontr = ArticleController(current_user.id)
    processed_articles = _articles_to_json(acontr.read_light(**filters))
    acontr.update(filters, {'readed': True})
    return processed_articles


@current_app.route('/fetch', methods=['GET'])
@current_app.route('/fetch/<int:feed_id>', methods=['GET'])
@login_required
def fetch(feed_id=None):
    """
    Triggers the download of news.
    News are downloaded in a separated process.
    """
    if conf.CRAWLING_METHOD == "default" \
            and (not conf.ON_HEROKU or current_user.is_admin):
        misc_utils.fetch(current_user.id, feed_id)
        flash(gettext("Downloading articles..."), "info")
    else:
        flash(gettext("The manual retrieving of news is only available " +
                      "for administrator, on the Heroku platform."), "info")
    return redirect(redirect_url())
