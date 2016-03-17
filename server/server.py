#!/usr/bin/env python2.7

import os
import sys
import time
import datetime
import tornado.httpserver
import tornado.ioloop
import tornado.web
import tornado.options

from tornado.options import define, options
define("port", default=8080, help="run on the given port", type=int)

SRC = os.path.abspath(os.path.join(os.path.dirname(os.path.realpath(__file__)), os.pardir))
WORKSPACE = SRC + '/workspace'
RRDB_PATH = WORKSPACE + '/rrdb'
LIB_PATH = SRC + '/lib'
sys.path.insert(0, LIB_PATH)
import common
import result

class Application(tornado.web.Application):
    def __init__(self):
        handlers = [
                (r"/", IndexHandler),
                (r"/results$", ResultsHandler),
                (r"/results/([\w-]+$)", ResultsHandler)
                #(r"/stats/([\w-\d]+)/(plot)$", ResultsHandler, dict(common_string='Value defined in Application')),
        ]

        tornado.web.Application.__init__(self, handlers, debug=True)

class IndexHandler(tornado.web.RequestHandler):
    def get(self):
        greeting = self.get_argument('greeting', 'Hello')
        self.write(greeting + ', friendly user!')

class PlotHandler(tornado.web.RequestHandler):
    def initialize(self, common_string):
        self.common_string = common_string

    def get(self, plot_id):
        response = { 'plot': plot_id,
                     'name':'Plot test results',
                     'common_string': self.common_string
                     }
        self.write(response)

class ResultsHandler(tornado.web.RequestHandler):
    def get(self, testcase_name=None):
        if testcase_name:
            result.plot_rrdbs(testcase_name)
        else:
            pass

    def post(self):
        files = self.request.files
        testbox = self.get_argument("testbox")
        rootfs = self.get_argument("rootfs")
        commit = self.get_argument("commit")
        unit_job = self.get_argument("unit_job")
        start_time = self.get_argument("start_time")

        testcase = self.get_argument("testcase")
        upload_path = WORKSPACE + '/tmp'
        if not os.path.exists(upload_path):
            os.makedirs(upload_path, 02775)

        for k, v in files.iteritems():
            for file_meta in v:
                filename = file_meta['filename']
                filepath = os.path.join(upload_path, filename)
                with open(filepath, 'w') as up:
                    up.write(file_meta['body'])
                if 'tar.gz' in filepath:
                    common.extract_tar_gz(filepath, WORKSPACE)
                    os.remove(filepath)
            self.write('Upload %s successfully!\n' % filename)
            if not os.path.exists(RRDB_PATH):
                os.makedirs(RRDB_PATH, 02775)
            # rrdb_file will be unicode str, rrdtool not support it
            rrdb_file = str(RRDB_PATH + '/' + testbox + "--" + testcase + '.rrd')
            result_path = '%s/results/%s/%s/%s/%s' % (WORKSPACE, testbox, rootfs + '-' + commit, unit_job, start_time)
            result.update_rrdbs(testcase, rrdb_file, start_time, result_path)
            result.plot_rrdbs(testcase)


if __name__ == "__main__":
    tornado.options.parse_command_line()
    http_server = tornado.httpserver.HTTPServer(Application())
    http_server.listen(options.port)
    tornado.ioloop.IOLoop.instance().start()
