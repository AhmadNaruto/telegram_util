#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import traceback as tb
import urllib.request
import threading
from bs4 import BeautifulSoup
import requests
import re
import time
import datetime as dt

name = 'telegram_util'

def log(*args):
	text = ' '.join([str(x) for x in args])
	with open('nohup.out', 'a') as f:
		f.write('%d:%d %s\n' % (dt.datetime.now().hour, dt.datetime.now().minute, text))

class AlbumResult(object):
	def __init__(self):
		self.imgs = []
		self.cap = ''
		self.video = ''
		self.cap_html = '' # weibo status only
		self.title = '' # weibo status only
		self.wid = '' # weibo status only 
		self.rwid = '' # weibo status only retweet id

	def empty(self):
		return (not self.imgs) and (not self.cap) and (not self.video)

	def __str__(self):
		return '\t'.join([k + ':' + str(v) for (k,v) in self.__dict__.items() if v])

def compactText(text):
	for _ in range(10):
		text = text.replace('  ', ' ')
		text = text.replace('\n ', '\n')
		text = text.replace(' \n', '\n')
	for _ in range(10):	
		text = text.replace('\n\n\n', '\n\n')
	return text.strip()

def escapeMarkdown(text):
	in_bracket = False
	r = []
	for x in text:
		if x in ['[', '(']:
			in_bracket = True
		if x in [')', ']']:
			in_bracket = False
		if not in_bracket and x == '_':
			r.append("\\")
		r.append(x)
	text = ''.join(r)
	for special_char in ['`', '*', 'https://', 'http://']:
		text = text.replace(special_char, '')
	text = text.replace('t.cn/', ' t.cn/')
	return compactText(text)

def getWid(url):
	url = clearUrl(url)
	if 'id=' in url:
		return url[url.find('id=') + 3:].split('&')[0]
	return url.split('/')[-1]
		
def cutCaption(quote, suffix, limit):
	quote = quote.strip()
	suffix = suffix.strip()
	if not quote:
		result = suffix
	elif len(quote) + len(suffix) > limit:
		result = quote[:limit - len(suffix)] + '... ' + suffix
	else:
		result = quote + ' ' + suffix
	return escapeMarkdown(result)

def isCN(title):
	if re.search(u'[\u4e00-\u9fff]', title):
		return True
	return False

TO_CLEAN = '#/?'
def cleanFileName(name):
	for x in TO_CLEAN:
		name = name.replace(x, '')
	return name

def getSoup(url):
	headers = {'Host':'telete.in',
		'Connection':'keep-alive',
		'Cache-Control':'max-age=0',
		'Upgrade-Insecure-Requests':'1',
		'User-Agent':'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.70 Safari/537.36',
		'Sec-Fetch-User':'?1',
		'Accept':'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3',
		'Sec-Fetch-Site':'none',
		'Sec-Fetch-Mode':'navigate',
		'Accept-Encoding':'gzip, deflate, br',
		'Accept-Language':'en-US,en;q=0.9,zh;q=0.8,zh-CN;q=0.7'}
	r = requests.get(url, headers=headers)
	return BeautifulSoup(r.text, 'html.parser')

def getChat(bot, text):
	text = text.split('/')[-1]
	if not text.startswith('@'):
		try:
			int(text)
		except:
			text = "@" + text
	return bot.getChat(text)

def getDisplayChat(chat):
	if chat.username:
		return '[' + chat.title + '](t.me/' + str(chat.username) + ')'
	else:
		return chat.title

def formatChat(bot, chat_id):
	try:
		chat = bot.getChat(chat_id)
		return getDisplayChat(chat)
	except:
		return str(chat_id)

def log_on_fail(debug_group = None, error_to_ignore=[]):
	def decorate(f):
		def applicator(*args, **kwargs):
			try:
				f(*args,**kwargs)
			except Exception as e:
				if str(e) in error_to_ignore:
					return
				print(e)
				tb.print_exc()
				if debug_group:
					debug_group.send_message(text=str(e)) 
		return applicator
	return decorate

def getDisplayUser(user):
	result = ''
	if user.first_name:
		result += user.first_name
	if user.last_name:
		result += ' ' + user.last_name
	if user.username:
		result += ' (' + user.username + ')'
	return '[' + result + '](tg://user?id=' + str(user.id) + ')'

def splitCommand(text):
	if not text:
		return '', ''
	pieces = text.split()
	if len(pieces) < 1:
		return '', ''
	command = pieces[0]
	return command.lower(), text[text.find(command) + len(command):].strip()

def tryDelete(msg):	
	try:	
		msg.delete()	
	except:	
		pass

def autoDestroy(msg, minutes=1):
	if msg.chat_id > 0:
		return
	threading.Timer(minutes * 60, lambda: tryDelete(msg)).start() 

class TimedDeleter():
	def __init__(self):
		self.queue = []
		self.scheduled = False

	def process(self):
		new_queue = []
		while self.queue:
			t, msg = self.queue.pop()
			if t < time.time():
				tryDelete(msg)
			else:
				new_queue.append((t, msg))
		self.queue = new_queue
		if not self.queue:
			self.scheduled = False
			return
		self.queue.sort()
		threading.Timer(self.queue[0][0] - time.time() + 30, lambda: self.process()).start() 

	def delete(self, msg, minutes=0):
		if minutes < 0.1:
			return tryDelete(msg)
		delete_time = time.time() + minutes * 60
		self.queue.append((delete_time, msg))
		if not self.scheduled:
			self.scheduled = True
			threading.Timer(delete_time - time.time() + 30, lambda: self.process()).start() 


def matchKey(t, keys):
	if not t:
		return False
	for k in keys:
		if k.lower() in t.lower():
			return True
	return False

def isUrl(t):
	for key in ['telegra.ph', 'com/', 'org/', '.st/', 'http', 't.co/']:
		if key in t:
			return True
	return False

def parseUrl(t):
	r = t
	for x in t.split():
		if not isUrl(x):
			continue
		if '://' in x:
			x = x[x.find('://') + 3:]
		else:
			r = r.replace(x, 'https://'+ x)
		for s in x.split('/'):
			if '?' in s:
				continue
			r = r.replace(s, urllib.request.pathname2url(s))
	return r

def isMeaningful(msg):
	if msg.media_group_id:
		return False
	if msg.text and 'bot_ignore' in msg.text:
		return False
	if msg.photo or msg.document or msg.video or msg.poll:
		return True
	if not msg.text:
		return False
	if msg.text[0] == '/':
		return False
	return len(msg.text) > 10

def _getFile(msg):
	file = None
	if msg.photo:
		file = msg.photo[-1]
	elif msg.video:
		file = msg.video
	if not file:
		return
	return file.get_file()

def getFilePath(msg):
	file = _getFile(msg)
	if file:
		return file.file_path

def getTmpFile(msg):
	file = _getFile(msg)
	if not file:
		return
	filename = 'tmp' + file.file_path.strip().split('/')[-1]
	file.download(filename)
	return filename

def addToQueue(update, queue, subscription):
	msg = update.effective_message 
	if not msg or not msg.chat:
		return
	if msg.chat.id not in subscription:
		return
	queue.append((msg.chat.id, msg.message_id))

def getLinkFromMsg(msg):
	for item in msg.entities:
		if matchKey(item["type"], ['url', 'link']):
			url = msg.text[item["offset"]:][:item["length"]]
			if not '://' in url:
				url = "https://" + url
			return url

def clearUrl(url):
	for end_char in ['/?utm_source', '?mblogid']:
		url = url.split(end_char)[0]
	for end_char in ['#']:
		if 'id=' not in url:
			url = url.split(end_char)[0]
	if matchKey(url, ['weibo', 'thepaper', 'm.sohu']) and 'id=' not in url: 
		url = url.split('?')[0]
	if url.endswith('/'):
		url = url[:-1]
	return url