from tkinter import *
import tkinter.messagebox
from PIL import Image, ImageTk
import socket, threading, os
from pathlib import Path
from time import sleep

from RtpPacket import *



CACHE_FILE_NAME = "cache-"
CACHE_FILE_EXT = ".jpg"
CACHE_DIR = Path("./cache")




class Client:
	INIT = 0
	READY = 1
	PLAYING = 2
	state = INIT
	
	SETUP = 0
	PLAY = 1
	PAUSE = 2
	TEARDOWN = 3
	

	# Initiation..
	def __init__(self, master, serveraddr, serverport, rtpport, filename):
		self.master = master
		self.master.protocol("WM_DELETE_WINDOW", self.handler)
		self.createWidgets()
		self.serverAddr = serveraddr
		self.serverPort = int(serverport)
		self.rtpPort = int(rtpport)
		self.fileName = filename
		self.rtspSeq = 0
		self.sessionId = 0
		self.frameNbr = 0  		#the number of the last frame received (start at 1)

		self.rtpSocket = None
		self.rtspSocket = None

		#make sure that the cache directory exists
		if not os.path.isdir(CACHE_DIR):
			os.mkdir(CACHE_DIR, mode=0o777)
		
		

	# THIS GUI IS JUST FOR REFERENCE ONLY, STUDENTS HAVE TO CREATE THEIR OWN GUI 	
	def createWidgets(self):
		"""Build GUI."""
		
		# Create Pause button			
		self.pause = Button(self.master, width=20, padx=5, pady=5)
		self.pause["text"] = "Pause"
		self.pause["command"] = self.pauseMovie
		self.pause.grid(row=1, column=0, padx=(80, 10), pady=5)
		
		# Create Play button		
		self.start = Button(self.master, width=20, padx=5, pady=5)
		self.start["text"] = "Play"
		self.start["command"] = self.playMovie
		self.start.grid(row=1, column=1, padx=10, pady=5)

		# Create Teardown button
		self.teardown = Button(self.master, width=20, padx=5, pady=5)
		self.teardown["text"] = "Stop"
		self.teardown["command"] =  self.exitClient
		self.teardown.grid(row=1, column=2, padx=(10, 80), pady=5)
		
		#placeholder canvas
		self.canvas = Canvas(self.master, height=350)
		self.canvas.grid(row=0, column=0, columnspan=3, sticky=W+E+N+S, padx=5, pady=5)


		# Create a label to display the movie
		self.label = Label(self.master)
		self.label.grid(row=0, column=0, columnspan=3, sticky=W+E+N+S, padx=5, pady=5) 
	


	def setupMovie(self):
		"""Setup RTSP connection with server."""
		self.rtspSeq = 0
		self.numRtpPacket = 0   #number of RTP packets received in a session

		#open RTSP soclet annd connect to server
		self.connectToServer()

		#send SETUP RTSP request
		self.sendRtspRequest(self.SETUP)

		reply = self.recvRtspReply()

		if reply["statusCode"] != 200:
			#an error occured
			print("SETUP failed!")
			return

		#get the session id from server
		self.sessionId = reply["session"]

		#create a RTP socket to start receiving RTP packets
		self.openRtpPort()
		
		#change the client's state to READY
		self.state = self.READY



	def exitClient(self):
		"""Teardown button handler."""
		if self.state != self.INIT:
			#change client's state to INIT
			self.state = self.INIT

			#send TEARDOWN RTSP requuest
			self.sendRtspRequest(self.TEARDOWN)

			#receive server's RTSP reply
			reply = self.recvRtspReply()
			
			if reply["statusCode"] != 200:
				#an error occurred
				print("TEARDOWN failed!")
				return

			#close the RTP socket
			self.rtpSocket.close()

			#close RTSP socket => end session here
			self.rtspSocket.close()

			#diplay some logging
			print("============= SESSION LOG =============")
			print(f"Number of RTP packets received: {self.numRtpPacket}\n")
			
			
			

	def pauseMovie(self):
		"""Pause button handler."""
		if self.state == self.PLAYING:
			#change the client's state to READY
			self.state = self.READY

			#send PAUSE RTSP request
			self.sendRtspRequest(self.PAUSE)

			reply = self.recvRtspReply()

			if reply["statusCode"] != 200:
				#an error occurred
				print("PAUSE failed!")
			
	

	def playMovie(self):
		"""Play button handler."""
		if self.state == self.INIT:
			#automatically set up when user presses Play button (if needed)
			self.setupMovie()
			

		if self.state == self.READY:
			#send the PLAY RTSP request
			self.sendRtspRequest(self.PLAY)

			reply = self.recvRtspReply()

			if reply["statusCode"] != 200:
				#an error occurred
				print("PLAY failed!")
				return

			self.state = self.PLAYING

			#start receiving RTP packets
			self.worker = threading.Thread(target=self.listenRtp)
			self.worker.start()



	def listenRtp(self):		
		"""Listen for RTP packets."""

		while True:
			data = self.rtpSocket.recvfrom(65536)[0]

			if data == b'\x00':
				#UDP packet containing 1 null byte indicates that the server has stopped sending RTP packets
				# => client sent PAUSE/TEARDOWN request or the server has sent all frames

				if self.state == self.PLAYING:
					#the server has sent all frames
					self.exitClient()

				break

			#de-serialize the RTP packet
			packet = RtpPacket()
			packet.decode(data)

			self.numRtpPacket += 1

			#the sequence number of received frame
			self.frameNbr = packet.seqNum()
			
			#write the frame to the cache file
			imageFile = self.writeFrame(packet.getPayload())

			#display the frame
			self.updateMovie(imageFile)

		
				
	def writeFrame(self, data):
		"""Write the received frame to a temp image file. Return the image file."""
		imageFileName = CACHE_FILE_NAME + str(self.frameNbr) + CACHE_FILE_EXT
		imageFile = CACHE_DIR / imageFileName

		with open(imageFile, "wb") as f:
			f.write(data)

		return imageFile
	

	def updateMovie(self, imageFile):
		"""Update the image file as video frame in the GUI."""
		frame = ImageTk.PhotoImage(Image.open(imageFile))

		self.label.configure(image=frame)
		self.label.image = frame
		

		
	def connectToServer(self):
		"""Connect to the Server. Start a new RTSP/TCP session."""
		#create the RTSP socket (TCP socket)
		self.rtspSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

		#create TCP connection with server
		self.rtspSocket.connect((self.serverAddr, self.serverPort))

	

	def sendRtspRequest(self, requestCode):
		"""Send RTSP request to the server."""	
		#-------------
		# TO COMPLETE
		#-------------
		request = ""

		if requestCode == self.SETUP:
			request = f"SETUP {self.fileName} RTSP/1.0\nCSeq: {self.rtspSeq}\nTransport: RTP/UDP; client_port= {self.rtpPort}"

		elif requestCode == self.PLAY:
			request = f"PLAY {self.fileName} RTSP/1.0\nCSeq: {self.rtspSeq}\nSession: {self.sessionId}"

		elif requestCode == self.PAUSE:
			request = f"PAUSE {self.fileName} RTSP/1.0\nCSeq: {self.rtspSeq}\nSession: {self.sessionId}"

		elif requestCode == self.TEARDOWN:
			request = f"TEARDOWN {self.fileName} RTSP/1.0\nCSeq: {self.rtspSeq}\nSession: {self.sessionId}"


		self.rtspSocket.send(request.encode())
		self.rtspSeq += 1  	#each time a RTSP request is sent the sequence number increases by 1

	
	
	def recvRtspReply(self):
		"""Receive RTSP reply from the server."""
		data = self.rtspSocket.recv(256)
		print(f'Data received:\n{data.decode("utf-8")}\n')

		return self.parseRtspReply(data.decode("utf-8"))
		



	def parseRtspReply(self, data):
		"""Parse the RTSP reply from the server."""
		#the server only sends RTSP reply when the status code is 200,
		#so we don't need to parse the status code and message (skip the first line)
		reply = {}

		lines = data.split("\n")

		if len(lines) == 3:
			#200 OK 
			reply["statusCode"] = 200
			reply["seq"] = int(lines[1].split(" ")[1])
			reply["session"] = int(lines[2].split(" ")[1])
		else:
			#404 or 500 error code
			reply["statusCode"] = int(lines[0].split(" ")[1])

		return reply

	

	def openRtpPort(self):
		"""Open RTP socket binded to a specified port."""
		#UDP socket for receiving RTP packets
		self.rtpSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

		#bind to a specific port to start receiving RTP packets   
		self.rtpSocket.bind(('', self.rtpPort))

		#set the timeout on the socket to 0.5 seconds
		self.rtpSocket.settimeout(0.5)
		


	def handler(self):
		"""Handler on explicitly closing the GUI window."""
		#send TEARDOWN request and close the RTP socket
		self.exitClient()

		self.master.destroy()


		

