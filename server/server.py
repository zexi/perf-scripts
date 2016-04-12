#!/usr/bin/env python

import os
import sys
import logging.config
import yaml
import copy
import tornado.httpserver
import tornado.ioloop
import tornado.web
import tornado.options
from tornado.options import define, options

SRC = os.path.abspath(os.path.join(os.path.dirname(os.path.realpath(__file__)), os.pardir))
WORKSPACE = SRC + '/workspace'
RRDB_PATH = WORKSPACE + '/rrdb'
LOG_PATH = WORKSPACE + '/logs'
LOG_FILE = LOG_PATH + '/server.log'
LIB_PATH = SRC + '/lib'
sys.path.insert(0, LIB_PATH)
import common
import mongodb
import result
import influxdb_pst

# load server config
conf_dict = common.load_conf(SRC + '/etc/pst_server.yaml')
server_port = str(conf_dict['pst_server']['port'])
os.environ['INFLUXDB_HOST'] = str(conf_dict['influxdb']['ip'])
os.environ['INFLUXDB_PORT'] = str(conf_dict['influxdb']['port'])
os.environ['INFLUXDB_USER'] = str(conf_dict['influxdb']['user'])
os.environ['INFLUXDB_PASS'] = str(conf_dict['influxdb']['pass'])

define("port", default=server_port, help="run on the given port", type=int)

DIFF_SUB_TEST = ['sysbench']

class Application(tornado.web.Application):
    def __init__(self):
        handlers = [
                (r"/", IndexHandler),
                (r"/results$", ResultsHandler),
                (r"/results/([\w-]+$)", ResultsHandler)
        ]
        settings = dict(
                template_path=os.path.join(os.path.dirname(__file__), "templates"),
                static_path=os.path.join(os.path.dirname(__file__), "static"),
                ui_modules={'Item': ItemModule, 'PicContent': PicContentModule, 'Pic': PicModule },
                debug=True
                )
        conn = mongodb.client('localhost', 27017)
        self.db = conn["pst"]
        self.influxdb_client = influxdb_pst.conn()
        influxdb_pst.create_db(self.influxdb_client)
        tornado.web.Application.__init__(self, handlers, **settings)

class ItemModule(tornado.web.UIModule):
    def render(self, item):
        return self.render_string('modules/item.html', item=item)

class PicContentModule(tornado.web.UIModule):
    def render(self, pics_dict):
        return self.render_string('modules/pic_content.html', pics_dict=pics_dict)

class PicModule(tornado.web.UIModule):
    def render(self, prefix, pics):
        return self.render_string('modules/pic.html', prefix=prefix, pics=pics)

class IndexHandler(tornado.web.RequestHandler):
    def get(self):
        self.render('index.html', pics_dict=result.get_testcase_pic())

class ResultsHandler(tornado.web.RequestHandler):
    def get(self, testcase_name=None):
        if testcase_name:
            pass
        else:
            pass

    def post(self):
        files = self.request.files
        testbox = self.get_argument("testbox")
        rootfs = self.get_argument("rootfs")
        commit = self.get_argument("commit")
        start_time = self.get_argument("start_time")
        testcase = self.get_argument("testcase")
        job_params = self.get_argument("job_params")

        db_coll = self.application.db.results
        influxdb_client = self.application.influxdb_client

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
            # rrdb_file will be unicode str, rrdtool not support it
            testcase_prefix = '%s/%s/%s/%s/%s' % (testcase, job_params, testbox, rootfs, commit)
            rrdb_file = str(RRDB_PATH + '/' + testcase_prefix + '/record.rrd')

            influxdb_tags = {
                'testcase': testcase,
                'job_params': job_params,
                'testbox': testbox,
                'rootfs': rootfs,
                'commit': commit,
            }

            # record testcase info to mongodb
            mongodb_info = copy.deepcopy(influxdb_tags)
            mongodb_info['rrdb_file'] = rrdb_file
            mongodb.coll_insert(db_coll, mongodb_info)

            if not os.path.exists(RRDB_PATH + '/' + testcase_prefix):
                os.makedirs(RRDB_PATH + '/' + testcase_prefix, 02775)
            result_path = '%s/results/%s/%s' % (WORKSPACE, testcase_prefix, start_time)
            if testcase in DIFF_SUB_TEST:
                result.update_rrdbs(str(testcase), rrdb_file, start_time, result_path, influxdb_client, influxdb_tags, job_params)
                result.plot_rrdbs(db_coll, testcase_prefix, accord_param=True)
            else:
                result.update_rrdbs(str(testcase), rrdb_file, start_time, result_path, influxdb_client, influxdb_tags)
                result.plot_rrdbs(db_coll, testcase_prefix)

def init_log():
    if not os.path.exists(LOG_PATH):
        os.makedirs(LOG_PATH, 02775)
    if not os.path.exists(LOG_FILE):
        os.system("touch %s" % LOG_FILE)

    dict_conf = yaml.load(open(SRC + '/etc/server_log.yaml', 'r'))
    dict_conf['handlers']['all']['filename'] = LOG_FILE
    logging.config.dictConfig(dict_conf)
    logging.info("Starting torando web server")

if __name__ == "__main__":
    tornado.options.parse_command_line()
    init_log()
    http_server = tornado.httpserver.HTTPServer(Application())
    http_server.listen(options.port)
    tornado.ioloop.IOLoop.instance().start()
