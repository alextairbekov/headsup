import csv
import cStringIO as StringIO
import json
import logging

from flask import Flask, jsonify, request, send_from_directory
from flask_sqlalchemy import *
import praw
import requests
import signal
import redis
import random

app = Flask(__name__)

# Create an instance of SQLAlchemy
db = SQLAlchemy(app)

# Start redis instance with default parameters
redis_instance = redis.StrictRedis(host='localhost', port=6379)


class Record(db.Model):
    id = db.Column(db.Integer, db.Sequence('record_reg_id', start=1, increment=1), primary_key=True)
    key = db.Column(db.String(80), nullable=False)
    value = db.Column(db.String(80), nullable=False)
    record_source = db.Column(db.String(80), nullable=False)


def filter_records_by(message):
    source = message['data']
    try:
        records = Record.query.filter_by(record_source=source).order_by('key').all()
        ret = {'records': [{'timestamp': r.key, 'value': r.value} for r in records]}
    except:
        ret = "" 
    redis_instance.publish('db-records-filter-'+source, json.dumps(ret))


def commit_new_record(message):
    username, timecr, comment = message['data'].split(':', 2)
    try:
        new_entry = Record(key=timecr, value=len(comment), record_source='comments for '+username)
        logging.debug('new record constructed!')
        db.session.add(new_entry)
        logging.debug('new record added!')
        db.session.commit()
        logging.debug('new record committed!')
        ret = {'Status': 'success!'}
    except:
        ret = {'Status': 'failure on input "%s"'.format(message['data'])} 
    redis_instance.publish('db-records-commit-'+username+':'+timecr, json.dumps(ret))
  

db_subscriber = redis_instance.pubsub(ignore_subscribe_messages=True)
db_subscriber.subscribe(**{'db-records-filter': filter_records_by, 'db-records-commit': commit_new_record})
thread = db_subscriber.run_in_thread(sleep_time=0.001)

@app.route("/api", methods=['GET'])
def hello():

    source = request.args.get('dataset')
    source = '*' if source is None else str(source)

    response_subscriber = redis_instance.pubsub(ignore_subscribe_messages=True)
    response_subscriber.subscribe('db-records-filter-'+source)

    if redis_instance.sadd('set:db-records-filter', source) == 1:
        redis_instance.publish('db-records-filter', source)

    for message in response_subscriber.listen():
        redis_instance.srem('set:db-records-filter', source)
        status_code = 200 if message['data'] != '""' else 400 
        response = app.response_class(response=message['data'], status=status_code, mimetype='application/json')
        break

    response_subscriber.close()
    return response


def publish_add_request(username='cruyff8', timecr=None, comment=None):
    timecr = time.time() if timecr is None else timecr
    
    response_subscriber = redis_instance.pubsub(ignore_subscribe_messages=True)
    response_subscriber.subscribe('db-records-commit-'+username+':'+str(timecr))
    redis_instance.publish('db-records-commit', username+':'+str(timecr)+':'+comment)

    for message in response_subscriber.listen():
        status_code = 201 if 'failure' not in message['data'] else 400
        response = app.response_class(response=message['data'], status=status_code, mimetype='application/json')
        break

    response_subscriber.close()
    return response 


@app.route('/api/new', methods=['POST'])
def add_comment(username='cruyff8', timecr=None, comment=None):

    timecr = str(time.time()) if timecr is None else timecr
    comment = request.args.get('comment') if comment is None else comment
    if comment is None:
        return jsonify({'Status': "'comment' is None"}), 400 
    return json.dumps("")
    # return publish_add_request(username=username, timecr=timecr, comment=comment)

    # response_subscriber = redis_instance.pubsub(ignore_subscribe_messages=True)
    # response_subscriber.subscribe('db-records-commit-'+username+':'+str(timecr))
    # redis_instance.publish('db-records-commit', username+':'+str(timecr)+':'+comment)

    # for message in response_subscriber.listen():
    #     status_code = 201 if 'failure' not in message['data'] else 400
    #     response = app.response_class(response=message['data'], status=status_code, mimetype='application/json')
    #     break

    # response_subscriber.close()
    # return response 

@app.route('/api', methods=['POST'])
def hello_add(data=None):
    if data is None:
        data = request.args.post('data')
    if data is None or data[0] is None or data[1] is None or data[2] is None:
        return jsonify({'Status': "'data' is None"}), 400
    return publish_add_request(username=data[0], timecr=data[1], comment=data[2])
    # return add_comment(username=data[0], timecr=data[1], comment=data[2])
    # return json.dumps("")

def get_comments():
    to_db = StringIO.StringIO()
    try:
        username = request.args.get('username')
    except:
        username = 'cruyff8'

    r = praw.Reddit('Reddit comment dataset import')
    user = r.get_redditor(username)
    count = 0
    for c in user.get_comments(limit=None):
        item = [username, str(c.created_utc), c.body]
        try:
            hello_add(item)
            count = count + 1
        except:
            pass 
    return json.dumps('Imported {0} records'.format(count))


def close_handlers(signum, frame):
    thread.stop()
    db_subscriber.close()
    sys.exit(0)

@app.route('/', methods=['GET'])
def root():
    return send_from_directory('static', 'index.html')

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)

    signal.signal(signal.SIGINT, close_handlers)     

    # Recreate tables
    db.drop_all()
    db.create_all()
    db.session.commit()

    app.config.update(TESTING=True, DEBUG=True, JSONIFY_PRETTYPRINT_REGULAR=False, SQLALCHEMY_TRACK_MODIFICATIONS=False)

    get_comments()
    app.run(port=5001, debug=True)

