#!/usr/bin/env python
# -*- coding: utf-8 -*-

import gevent
import json
import os
import random
import redis
from flask import Flask, jsonify, render_template, request
from flask_sockets import Sockets

app = Flask(__name__)
app.config['SECRET_KEY'] = 'super secret'

sockets = Sockets(app)

r = redis.from_url(os.environ.get("REDIS_URL"))
CHANNEL = 'status-updates'


STATUSES = {
        'hackday': {
            'class': 'default',
            'primary': u'🕵<br/>hackday',
            'detail': u'In the Agora conference room',
            },
        'judging': {
            'class': 'default',
            'primary': u'Judging<br/>Hackday',
            'detail': u'In the Agora conference room',
            },
        'dnd': {
            'class': 'dnd',
            'primary': u'Can’t talk<br/>right now',
            'detail': u'But i’ll be happy to later!',
            },
        'wfh': {
            'class': 'wfh',
            'primary': u'Working<br/>from home',
            'detail': u'Ready to collaborate remotely!',
            },
        'out': {
            'class': 'out',
            'primary': u'Out of<br/>office',
            'detail': u'I’m unavailable today. Please see my manager if needed.'
            },
        'office-hours': {
            'class': 'office-hours',
            'primary': u'Holding<br/>office hours',
            'detail': u'Please feel free to stop by!',
            },
        'sick': {
            'class': 'sick',
            'primary': u'<span class="red">☣</span><br/>Out sick',
            'detail': u'Trust me; you don’t want me to be here.'
            },
        'vacation': {
            'class': 'out',
            'primary': u'🌴 🌅 🌴<br/>On Vacation',
            'detail': u'I’m completely off-the-grid.',
            },
        'snowboarding': {
            'class': 'out',
            'primary': u'❄️ 🏂 ❄️<br/>snowboarding',
            'detail': u'I’m out shreddin’ the gnar!',
            },
        'dragons': {
            'class': 'danger',
            'primary': u'there be<br/>🐲 dragons 🐉',
            'detail': u'approach at your own peril!',
            },
        'available': {
            'class': 'default',
            'primary': u'🙂<br/>I’m here',
            'detail': u'If you need me, let’s chat!',
            },
        }

DEFAULT = {
        'status': 'available',
        }


class UpdatesBackend(object):

    def __init__(self):
        self.clients = list()
        self.pubsub = r.pubsub()
        self.channel = CHANNEL
        self.pubsub.subscribe(self.channel)

    def __iter_data(self):
        for message in self.pubsub.listen():
            data = message.get('data')
            if message['type'] == 'message':
                app.logger.info(u'Sending message on {0}: {1}'.format(self.channel, data))
                yield data

    def register(self, client):
        self.clients.append(client)

    def send(self, client, data):
        try:
            client.send(data)
        except Exception:
            self.clients.remove(client)

    def run(self):
        for data in self.__iter_data():
            for client in self.clients:
                gevent.spawn(self.send, client, data)

    def start(self):
        gevent.spawn(self.run)

updates = UpdatesBackend()
updates.start()

@sockets.route('/submit')
def inbox(ws):
    while not ws.closed:
        gevent.sleep(0.1)
        message = ws.receive()

        if message:
            app.logger.info(u'Inserting message: {}'.format(message))
            r.publish(CHANNEL, message)

@sockets.route('/receive')
def outbox(ws):
    updates.register(ws)

    while not ws.closed:
        gevent.sleep(0.1)


@app.route('/')
def get_index():
    return render_template('index.html')

@app.route('/messages')
def messages():
    return render_template('messages.html')

@app.route('/random')
def random_status():
    status_data = random.choice(list(STATUSES.values()))
    return render_template('base.html', status=status_data)


def _make_combined_user_data(user_data, username=None):
    status = user_data.get('status')
    status_detail = STATUSES.get(status, {})
    if username is not None:
        user_data['username'] = username
    if not user_data.get('class'):
        user_data['class'] = status_detail.get('class', 'default')
    if not user_data.get('primary'):
        user_data['primary'] = status_detail.get('primary', "I'm here")
    if not user_data.get('detail'):
        user_data['detail'] = status_detail.get('detail', "If you need me, let's chat!")
    return user_data

@app.route('/<string:username>/status', methods=['GET'])
def get_user_status(username):
    username = username.lower()
    try:
        user_data = json.loads(r.get(username))
    except:
        user_data = {}
    if not user_data:
        user_data = DEFAULT
    user_data = _make_combined_user_data(user_data, username=username)
    return jsonify(user_data)

@app.route('/<string:username>/status', methods=['PUT'])
def put_user_status(username):
    username = username.lower()
    user_data = {
            }
    put_data = request.form
    for key in put_data.keys():
        user_data[key] = put_data[key]
    r.set(username, json.dumps(user_data))
    message = json.dumps(_make_combined_user_data(user_data, username=username))
    r.publish(CHANNEL, message)
    return jsonify(user_data)

@app.route('/<string:username>')
def get_user_sign(username):
    username = username.lower()
    try:
        user_data = json.loads(r.get(username))
    except:
        user_data = {}
    if not user_data:
        user_data = DEFAULT
    #    status_data = random.choice(list(STATUSES.values()))
    #    status_data = STATUSES['snowboarding']
    user_data = _make_combined_user_data(user_data, username=username)
    return render_template('base.html', status=user_data)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
