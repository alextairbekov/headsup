import csv
import cStringIO as StringIO
import json
import logging

from flask import Flask, jsonify, request, send_from_directory
from flask_sqlalchemy import *
import praw
import requests

app = Flask(__name__)

#Create an instance of SQLAclhemy
db = SQLAlchemy(app)

class Record(db.Model):
    id = db.Column(db.Integer, db.Sequence('record_reg_id', start=1, increment=1), primary_key=True)
    key = db.Column(db.String(80), nullable=False)
    value = db.Column(db.String(80), nullable=False)
    record_source = db.Column(db.String(80), nullable=False)


@app.route("/api", methods=['GET'])
def hello():
    source = request.args.get('dataset')
    if source is not None:
        records = Record.query.filter_by(record_source='source').order_by('key').all()
    else:
        records = Record.query.order_by('key').all()
    
    ret = {'records': [{'timestamp':r.key,'value': r.value} for r in records]}
    return jsonify(ret), 200

@app.route('/api', methods=['POST'])
def hello_add(data=None):
    if data is None:
        data = request.args.post('data')
    db.session.add(Record(record_source=data[0], key=data[1], value=data[2])) 
    db.session.commit()
    return json.dumps("")

def get_comments():
    to_db = StringIO.StringIO()
    try:
        username = request.args.get('username')
    except: 
        username = 'cruyff8'

    r = praw.Reddit('Reddit comment datatset import')
    user = r.get_redditor(username)
    count = 0
    for c in user.get_comments(limit=None):
        count = count + 1 
        item = ['comments for '+username, str(c.created_utc), str(len(c.body))]
        try:
            hello_add(item)
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
