from random import randint
import threading, socket, json, os
from pathlib import Path
from tkinter.constants import NO

from VideoStream import VideoStream
from RtpPacket import RtpPacket



VIDEO_DIR = Path('./video')


class ServerWorker:
	SETUP = 'SETUP'
	PLAY = 'PLAY'
	PAUSE = 'PAUSE'
	TEARDOWN = 'TEARDOWN'
	FORWARD = 'FORWARD'
	LIST = 'LIST'			#return list of available videos
	DESCRIBE = 'DESCRIBE'
	SWITCH = 'SWITCH'
	
	INIT = 0
	READY = 1
	PLAYING = 2
	PENDING = 3
	state = INIT

	OK_200 = 0
	FILE_NOT_FOUND_404 = 1
	CON_ERR_500 = 2
	

	clientInfo = {}
	
	def __init__(self, clientInfo):
		self.numRtpPacket = 0   #number of RTP packets sent in a session (for logging)
		self.clientInfo = clientInfo
		

	def run(self):
		self.clientInfo['event'] = threading.Event()
		self.mainThread = threading.Thread(target=self.recvRtspRequest)
		self.mainThread.start()
	
	

	def recvRtspRequest(self):
		"""Receive RTSP request from the client."""
		connSocket = self.clientInfo['rtspSocket'][0]

		while True:
			try:
				data = connSocket.recv(256)

				if data:
					print("Data received:\n" + data.decode("utf-8") + "\n")
					self.processRtspRequest(data.decode("utf-8"))
			except:
				#the client has sent TEARDOWN request => close session here
				address = self.clientInfo["rtspSocket"][1][0]
				port = int(self.clientInfo['rtpPort'])
				print(f"Session with client ({address}, {port}) closed.\n")

				#display some logging
				print("============= SESSION LOG =============")
				print(f"Client: ({address}, {port})")
				print(f"Number of RTP packets sent: {self.numRtpPacket}\n")

				break



	def processRtspRequest(self, data):
		"""Process RTSP request sent from the client."""
		# Get the request type
		request = data.split('\n')
		line1 = request[0].split(' ')
		requestType = line1[0]
		
		# Get the RTSP sequence number 
		seq = request[1].split(' ')
		
		# Process SETUP request
		if requestType == self.SETUP:
			if self.state == self.INIT:
				# Update state
				print("processing SETUP\n")
				# Get the media file name
				filename = line1[1]

				try:
					self.clientInfo['videoStream'] = VideoStream(VIDEO_DIR / filename)
					self.state = self.READY
				except IOError:
					self.replyRtsp(self.FILE_NOT_FOUND_404, seq[1])
					return
				
				# Generate a randomized RTSP session ID
				self.clientInfo['session'] = randint(100000, 999999)
				
				# Send RTSP reply
				numFrame = self.clientInfo['videoStream'].getNumFrame()
				body = json.dumps({
					"nframe": numFrame,
					"duration": int(numFrame * 0.064)
				})
				self.replyRtsp(self.OK_200, seq[1], body)
				

				# Get the RTP/UDP port from the last line
				self.clientInfo['rtpPort'] = request[2].split(' ')[3]
		

		elif requestType == self.FORWARD:
			if self.state != self.INIT:
				print("processing FORWARD\n")
				self.state = self.READY
				self.clientInfo['event'].set()

				frameNbr = int(request[3].split(": ")[1])
				self.clientInfo['videoStream'].moveTo(frameNbr)

				self.state = self.PLAYING
				self.clientInfo["rtpSocket"] = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

				self.replyRtsp(self.OK_200, seq[1])

				self.clientInfo['worker']= threading.Thread(target=self.sendRtp) 
				self.clientInfo['worker'].start()


		# Process PLAY request 		
		elif requestType == self.PLAY:
			if self.state == self.READY or self.state == self.PENDING:
				print("processing PLAY\n")
				self.state = self.PLAYING
				
				# Create a new socket for RTP/UDP
				self.clientInfo["rtpSocket"] = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
				
				self.replyRtsp(self.OK_200, seq[1])
				
				# Create a new thread and start sending RTP packets
				self.clientInfo['worker']= threading.Thread(target=self.sendRtp) 
				self.clientInfo['worker'].start()
		

		# Process PAUSE request
		elif requestType == self.PAUSE:
			if self.state == self.PLAYING:
				print("processing PAUSE\n")
				self.state = self.READY
				self.clientInfo['event'].set()
				self.replyRtsp(self.OK_200, seq[1])
		

		# Process TEARDOWN request
		elif requestType == self.TEARDOWN:
			print("processing TEARDOWN\n")
			self.state = self.INIT
			self.clientInfo['event'].set()
			self.replyRtsp(self.OK_200, seq[1])
			
			# Close the RTP socket
			if 'rtpSocket' in self.clientInfo:
				self.clientInfo['rtpSocket'].close()


			rtspSocket = self.clientInfo["rtspSocket"][0]
			rtspSocket.close()


		#Process LIST request (list all available videos)
		elif requestType == self.LIST:
			print("processing LIST\n")
			#get the list of files in video directory
			dirpath, dirname, filenames = list(os.walk(VIDEO_DIR))[0]
			self.videoList = filenames
			body = json.dumps({
				"list": self.videoList
			})
			self.replyRtsp(self.OK_200, seq[1], body=body)


		#Process LIST request (describe the current stream)
		elif requestType == self.DESCRIBE:
			# v = (protocol version)
			# o = (owner/creator and session identifier)
			# s = (session name)
			# i =* (session information)
			# u =* (URI of description)
			# e =* (email address)
			# p =* (phone number)
			# c =* (connection information - not required if included in all media)
			# b =* (bandwidth information)
			# z =* (time zone adjustments)
			# k =* (encryption key)
			# a =* (zero or more session attribute lines)
			print("processing DESCRIBE\n")
			description = {
				"v": 0,
				"o": f"elnosabe 2890844526 2890842807 IN IP4 126.16.64.4",
				"s": "Mjpeg Video Stream",
				"t": f"2873397496 2873404696",
				"a": "recvonly",
				"m": f"video {self.clientInfo['rtpPort']} RTP/AVP 26"
			}
			description_s = ""
			for key in description:
				description_s += f"{key}={description[key]}\n"
			body = json.dumps({"description": description_s})
			self.replyRtsp(self.OK_200, seq[1], body=body)


		#Process LIST request (describe the current stream)
		elif requestType == self.SWITCH:
			print("processing SWITCH\n")
			filename = line1[1]

			if self.state == self.PLAYING:
				#streaming is happening => stop the sendRtp thread
				self.clientInfo['event'].set()

			self.state = self.PENDING

			try:
				self.clientInfo["videoStream"] = VideoStream(VIDEO_DIR / filename)
			except IOError:
				#error opening the stream => 404
				self.replyRtsp(self.FILE_NOT_FOUND_404, seq[1])
				return

			numFrame = self.clientInfo['videoStream'].getNumFrame()
			body = json.dumps({
				"nframe": numFrame,
				"duration": int(numFrame * 0.064)
			})
			self.replyRtsp(self.OK_200, seq[1], body=body)

		


	def sendRtp(self):
		"""Send RTP packets over UDP."""
		while True:
			#send a frame every 50 miliseconds
			self.clientInfo['event'].wait(0.05)   
			
			# Stop sending if request is PAUSE or TEARDOWN
			if self.clientInfo['event'].isSet():
				self.clientInfo['event'].clear()
				break 
				
			data = self.clientInfo['videoStream'].nextFrame()

			if data:
				frameNumber = self.clientInfo['videoStream'].frameNbr()
				try:
					address = self.clientInfo['rtspSocket'][1][0]
					port = int(self.clientInfo['rtpPort'])
					self.clientInfo['rtpSocket'].sendto(self.makeRtp(data, frameNumber),(address,port))
				except:
					print("Connection Error")

				self.numRtpPacket += 1



	def makeRtp(self, payload, frameNbr):
		"""RTP-packetize the video data."""
		version = 2
		padding = 0
		extension = 0
		cc = 0
		marker = 0
		pt = 26 # MJPEG type
		seqnum = frameNbr
		ssrc = 0 
		
		rtpPacket = RtpPacket()
		
		rtpPacket.encode(version, padding, extension, cc, seqnum, marker, pt, ssrc, payload)
		
		return rtpPacket.getPacket()
		
		

	def replyRtsp(self, code, seq, body=None):
		"""Send RTSP reply to the client."""
		reply = ""

		if code == self.OK_200:
			print("OK 200\n")
			reply = f"RTSP/1.0 200 OK\nCSeq: {seq}\nSession: {self.clientInfo['session']}"

			if body:
				reply = reply + "\n" + body


		# Error messages
		elif code == self.FILE_NOT_FOUND_404:
			print("404 NOT FOUND")
			reply = 'RTSP/1.0 404 NOT FOUND'
		elif code == self.CON_ERR_500:
			print("500 CONNECTION ERROR")
			reply = 'RTSP/1.0 500 CONNECTION ERROR'


		connSocket = self.clientInfo['rtspSocket'][0]
		connSocket.send(reply.encode())

		
