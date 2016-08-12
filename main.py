import csv
import cStringIO as StringIO
import json
import logging

from flask import Flask, jsonify, request, send_from_directory
from flask_sqlalchemy import *
import praw
import requests

import redis

app = Flask(__name__)

# Create an instance of SQLAlchemy
db = SQLAlchemy(app)

# Start redis instance with default parameters
redis_instance = redis.StrictRedis(host='localhost', port=6379)


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
        ret = {'Status', 'success!'}
    except:
        ret = {'Status': 'failure on input "%s"'.format(message['data'])} 
    redis_instance.publish('db-records-commit-'+username+':'+timecr, json.dumps(ret))
  

db_subscriber = redis_instance.pubsub()
db_subscriber.subscribe(**{'db-records-filter': filter_records_by, 'db-records-commit': commit_new_record})

class Record(db.Model):
    id = db.Column(db.Integer, db.Sequence('record_reg_id', start=1, increment=1), primary_key=True)
    key = db.Column(db.String(80), nullable=False)
    value = db.Column(db.String(80), nullable=False)
    record_source = db.Column(db.String(80), nullable=False)


@app.route("/api", methods=['GET'])
def hello():

    source = request.args.get('dataset')
    source = '*' if source is None else str(source)

    response_subscriber = redis_instance.pubsub()
    response_subscriber.subscribe('db-records-filter-'+source)

    if redis_instance.sadd('set:db-records-filter', source) == 1:
        redis_instance.publish('db-records-filter', source)

    for message in response_subscriber.listen():
        redis_instance.srem('set:db-records-filter', source)
        status = 200 if message['data'] != '""' else 400 
        response = app.response_class(data=message['data'], status_code=status, mimetype='application/json')
        break

    response_subscriber.close()
    return response


@app.route('/api/new', methods=['POST'])
def add_comment(timecr = time.time(), username='cruyff8', comment=None):
   
    if comment is None: 
        comment = request.args.get('comment')
    if comment is None:
        return jsonify({'Status': "'comment' is None"}), 400 

    response_subscriber = redis_instance.pubsub()
    response_subscriber.subscribe('db-records-commit-'+username+':'+str(timecr))
    redis_instance.publish('db-records-commit', username+':'+str(createtime)+':'+comment)

    for message in response_subscriber.listen():
        status = 201 if 'failure' not in message['data'] else 400
        response = app.response_class(data=message['data'], status_code=status, mimetype='application/json')
        break

    response_subscriber.close()
    return response 

@app.route('/api', methods=['POST'])
def hello_add(data=None):
    
    if data is None:
        data = request.args.post('data')
    if data is None or data[0] is None or data[1] is None or data[2] is None:
        return jsonify({'Status': "'data' is None"}), 400

    return add_comment(username=data[0], timecr=data[1], comment=data[2])


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


@app.route('/', methods=['GET'])
def root():
    return send_from_directory('static', 'index.html')

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)

    # Recreate tables
    db.drop_all()
    db.create_all()
    db.session.commit()

    app.config.update(TESTING=True, DEBUG=True, JSONIFY_PRETTYPRINT_REGULAR=False, SQLALCHEMY_TRACK_MODIFICATIONS=False)
    get_comments()
    app.run(port=5001, debug=True)

    for msg in db_subscriber.listen():
        # for each message we have set up a handler
        pass
