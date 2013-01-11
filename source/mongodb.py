#! /usr/bin/env python
# -*- coding: utf-8 -*-

# pyAggr3g470r - A Web based news aggregator.
# Copyright (C) 2010-2013  Cédric Bonhomme - http://cedricbonhomme.org/
#
# For more information : http://bitbucket.org/cedricbonhomme/pyaggr3g470r/
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>

__author__ = "Cedric Bonhomme"
__version__ = "$Revision: 0.5 $"
__date__ = "$Date: 2012/03/03 $"
__revision__ = "$Date: 2012/12/02 $"
__copyright__ = "Copyright (c) Cedric Bonhomme"
__license__ = "GPLv3"

import pymongo

from operator import itemgetter, attrgetter

class Articles(object):
    """
    """
    def __init__(self, url='localhost', port=27017, db_name="pyaggr3g470r", user="", password=""):
        """
        Instantiates the connection.
        """
        self.db_name = db_name
        self.connection = pymongo.connection.Connection(url, port)
        self.db = pymongo.database.Database(self.connection, self.db_name)
        self.db.authenticate(user, password)

    def add_collection(self, new_collection):
        """
        Creates a new collection for a new feed.
        """
        collection = self.db[new_collection["feed_id"]]
        collection.create_index([("article_date", pymongo.DESCENDING)], {"unique":False, "sparse":False})
        collection.ensure_index('article_content', pymongo.ASCENDING)
        collection.insert(new_collection)

    def add_articles(self, articles, feed_id):
        """
        Add article(s) in a collection.
        """
        collection = self.db[str(feed_id)]
        #collection.create_index([("article_date", pymongo.DESCENDING)], {"unique":False, "sparse":False})
        #collection.ensure_index('article_content', pymongo.ASCENDING)
        print(collection.index_information())
        for article in articles:
            cursor = collection.find({"article_id":article["article_id"]})
            if cursor.count() == 0:
                collection.insert(article)

    def delete_feed(self, feed_id):
        """
        Delete a collection (feed with all articles).
        """
        self.db.drop_collection(feed_id)

    def delete_article(self, feed_id, article_id):
        """
        Delete an article.
        """
        collection = self.db[str(feed_id)]
        collection.remove(spec_or_id={"article_id":article_id}, safe=True)

    def get_feed(self, feed_id):
        """
        Return information about a feed.
        """
        return next(self.db[str(feed_id)].find())

    def get_all_feeds(self, condition=None):
        """
        Return all feeds object. The returned list
        is sorted by alphabetically (by feed name).
        """
        feeds = []
        collections = self.db.collection_names()
        for collection_name in collections:
            if collection_name != "system.indexes":
                if condition is None:
                    cursor = self.db[collection_name].find({"type":0})
                else:
                    cursor = self.db[collection_name].find({"type":0, condition[0]:condition[1]})
                if cursor.count() != 0:
                    feeds.append(next(cursor))
        feeds.sort(key = lambda elem: elem['feed_title'].lower())
        return feeds

    def get_articles(self, feed_id=None, article_id=None, condition=None, limit=1000000000):
        """
        Return one or several articles.
        The parameter "condition" is an optional requirement, for example:
        get_articles(feed_id, condition=("article_readed", False)) will
        return all unread articles of the feed 'feed_id'.
        """
        if feed_id == None and article_id == None:
            # Return all articles.
            articles = []
            collections = self.db.collection_names()
            for collection_name in collections:
                collection = self.db[collection_name]
                if condition is None:
                    articles.extend(collection.find({"type":1}, limit=limit))
                else:
                    articles.extend(collection.find({"type":1, condition[0]:condition[1]}, limit=limit))
            return articles

        elif feed_id != None and article_id == None:
            # Return all the articles of a collection.
            collection = self.db[str(feed_id)]
            if condition is None:
                cursor = collection.find({"type":1}, limit=limit)
            else:
                cursor = collection.find({"type":1, condition[0]:condition[1]}, limit=limit)
            return cursor.sort([("article_date", pymongo.DESCENDING)])

        elif feed_id != None and article_id != None:
            # Return a precise article.
            collection = self.db[str(feed_id)]
            return next(collection.find({"article_id":article_id}))

    def get_favorites(self, feed_id=None):
        """
        Return favorites articles.
        """
        if feed_id is not None:
            # only for a feed
            collection = self.db[feed_id]
            cursor = collection.find({'type':1, 'article_like':True})
            return cursor.sort([("article_date", pymongo.DESCENDING)])
        else:
            favorites = []
            for feed_id in self.db.collection_names():
                favorites += self.get_favorites(feed_id)
            return favorites

    def nb_articles(self, feed_id=None):
        """
        Return the number of articles of a feed
        or of all the database.
        """
        if feed_id is not None:
            collection = self.db[feed_id]
            cursor = collection.find({'type':1})
            return cursor.count()
        else:
            nb_articles = 0
            for feed_id in self.db.collection_names():
               nb_articles += self.nb_articles(feed_id)
            return nb_articles

    def nb_unread_articles(self, feed_id=None):
        """
        Return the number of unread articles of a feed
        or of all the database.
        """
        if feed_id is not None:
            return self.get_articles(feed_id=feed_id, condition=("article_readed", False)).count()
        else:
            return len(self.get_articles(condition=("article_readed", False)))

    def like_article(self, like, feed_id, article_id):
        """
        Like or unlike an article.
        """
        collection = self.db[str(feed_id)]
        collection.update({"article_id": article_id}, {"$set": {"article_like": like}})

    def nb_favorites(self, feed_id=None):
        """
        Return the number of favorites articles of a feed
        or of all the database.
        """
        if feed_id is not None:
            return self.get_favorites(feed_id).count()
        else:
            return len(self.get_favorites())

    def nb_mail_notifications(self):
        """
        Return the number of subscribed feeds.
        """
        nb_mail_notifications = 0
        for feed_id in self.db.collection_names():
            collection = self.db[feed_id]
            cursor = collection.find({'type':0, 'mail':True})
            nb_mail_notifications += cursor.count()
        return nb_mail_notifications

    def mark_as_read(self, readed, feed_id=None, article_id=None):
        """
        """
        if feed_id != None and article_id != None:
            collection = self.db[str(feed_id)]
            collection.update({"article_id": article_id, "article_readed":not readed}, {"$set": {"article_readed": readed}})
        elif feed_id != None and article_id == None:
            collection = self.db[str(feed_id)]
            collection.update({"type": 1, "article_readed":not readed}, {"$set": {"article_readed": readed}}, multi=True)
        else:
            for feed_id in self.db.collection_names():
                self.mark_as_read(readed, feed_id, None)

    def update_feed(self, feed_id, changes):
        """
        Update a feed.
        """
        collection = self.db[str(feed_id)]
        collection.update({"type": 0, "feed_id":feed_id}, {"$set": changes}, multi=True)

    def full_search(self, term):
        """
        Indexed full text search through content of articles.
        """
        articles = {}
        for collection in self.get_all_feeds():
            result = self.db[collection["feed_id"]].find({'article_content': {'$regex': term, "$options": 'i' }})
            if result.count() != 0:
                articles[collection["feed_id"]] = result.sort([("article_date", pymongo.DESCENDING)])
        return articles

    # Functions on database
    def drop_database(self):
        """
        Drop all the database
        """
        self.connection.drop_database(self.db_name)


if __name__ == "__main__":
    # Point of entry in execution mode.
    articles = Articles()
    # Create a collection for a stream
    collection_dic = {"collection_id": 42,\
                        "feed_image": "Image", \
                        "feed_title": "Title", \
                        "feed_link": "Link", \
                        "site_title": "Site link", \
                        "mail": True, \
                        }
    #articles.add_collection(collection_dic)

    # Add an article in the newly created collection
    article_dic1 = {"article_id": 51, \
                    "article_date": "Today", \
                    "article_link": "Link of the article", \
                    "article_title": "The title", \
                    "article_content": "The content of the article", \
                    "article_readed": True, \
                    "article_like": True \
                    }
    article_dic2 = {"article_id": 52, \
                    "article_date": "Yesterday", \
                    "article_link": "Link", \
                    "article_title": "Hello", \
                    "article_content": "The content of the article", \
                    "article_readed": True, \
                    "article_like": True \
                    }

    #articles.add_articles([article_dic1, article_dic2], 42)

    print("All articles:")
    #print articles.get_all_articles()


    # Drop the database
    articles.drop_database()
