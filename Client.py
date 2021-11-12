from tkinter import *
from PIL import Image, ImageTk
import socket, threading, os, json, copy
from pathlib import Path
import datetime
from time import sleep


from RtpPacket import *



CACHE_FILE_NAME = "cache-"
CACHE_FILE_EXT = ".jpg"
CACHE_DIR = Path("./cache")




class Client:
	INIT = 0
	READY = 1
	PLAYING = 2
	PENDING = 3
	state = INIT
	
	SETUP = 0
	PLAY = 1
	PAUSE = 2
	TEARDOWN = 3
	FORWARD = 4
	LIST = 5
	DESCRIBE = 6
	SWITCH = 7
	

	# Initiation..
	def __init__(self, master, serveraddr, serverport, rtpport, filename):
		self.master = master
		self.master.protocol("WM_DELETE_WINDOW", self.handler)

		self.videoLength = 0		#the length of the video (in seconds)
		self.sliderTick = 0			#the portion corresponding to 1 second on the time slider
		self.timeStamp1 = StringVar(value="00:00:00")
		self.timeStamp2 = StringVar(value="00:00:00")
		
		self.clockEvent = threading.Event()	#clear the event to pause the clock thread
		self.clockThread = None

		self.videoList = []
		self.listButtons = [None] * 3

		self.createWidgets()

		self.serverAddr = serveraddr
		self.serverPort = int(serverport)
		self.rtpPort = int(rtpport)
		self.fileName = filename
		self.rtspSeq = 0
		self.sessionId = 0
		self.frameNbr = 0  		#index of the currently playing frame (starting at 1)
		self.numFrame = 0		#total number of frames of the video

		self.rtpSocket = None
		self.rtspSocket = None

		

		#make sure that the cache directory exists
		if not os.path.isdir(CACHE_DIR):
			os.mkdir(CACHE_DIR, mode=0o777)

	

	# THIS GUI IS JUST FOR REFERENCE ONLY, STUDENTS HAVE TO CREATE THEIR OWN GUI 	
	def createWidgets(self):
		"""Build GUI."""
		# Create Pause button
		self.pause = Button(self.master, width=10, padx=10, pady=5)
		self.pause["text"] = "Pause"
		self.pause["command"] = self.pauseMovie
		self.pause.grid(row=6, column=2, padx=(100, 10), pady=(20, 10))
		
		# Create Play button		
		self.start = Button(self.master, width=10, padx=10, pady=5)
		self.start["text"] = "Play"
		self.start["command"] = self.playMovie
		self.start.grid(row=6, column=3, padx=10, pady=(20, 10))

		# Create Teardown button
		self.teardown = Button(self.master, width=10, padx=10, pady=5)
		self.teardown["text"] = "Stop"
		self.teardown["command"] =  self.exitClient
		self.teardown.grid(row=6, column=4, padx=(10,100), pady=(20, 10))

		# Create Describe button
		self.describe = Button(self.master, width=20, padx=10, pady=5, background="#f3e6d8")
		self.describe["text"] = "Describe"
		self.describe["command"] = self.describeStream
		self.describe.grid(row=0, column=0, padx=(40,10))

		# Create List button
		self.list = Button(self.master, width=20, padx=10, pady=5, background="#f3e6d8")
		self.list["text"] = "List Videos"
		self.list["command"] = self.getVideoList
		self.list.grid(row=1, column=0, padx=(40,10))

		for i in range(3):
			self.listButtons[i] = Button(self.master, width=20, height=3, padx=10)
		
		#video slider
		self.slider = Scale(
			self.master,
			orient=HORIZONTAL,
			width=10,		#thickness
			showvalue=0,	#do not show thw value of scale on top of the slider
			from_=0,		#lower bound
			to=100,			#upper bound
			troughcolor='#c6ebf6',
			command=self.updateTimeStamps
		)

		self.slider.grid(row=5, column=2, columnspan=3, sticky=W+E)
		self.slider.bind("<ButtonRelease-1>", self.forwardMovie)

		#timestamps diaplayed at the sides
		self.stamp1 = Label(self.master, width=10, textvariable=self.timeStamp1)
		self.stamp1.grid(row=5, column=1, sticky=S)

		self.stamp2 = Label(self.master,  width=10, textvariable=self.timeStamp2)
		self.stamp2.grid(row=5, column=5, sticky=S)

		#placeholder canvas
		self.canvas = Canvas(self.master, height=400)
		self.canvas.grid(row=0, column=1, columnspan=5, rowspan=5 ,sticky=W+E+N+S, padx=20, pady=20)

		# Create a label to display the movie
		self.label = Label(self.master, background='black')
		self.label.grid(row=0, column=1, columnspan=5, rowspan=5, sticky=W+E+N+S, padx=20, pady=20) 
	


	def clock(self):
		"""Move slider based on video's elapsed time"""
		while True:
			self.clockEvent.wait()
			
			if self.state == self.INIT:		#exitClient() is called
				break
			
			#move the slider every 1 second
			sleep(1)
			self.slider.set(float(self.slider.get()) + self.sliderTick)



	def updateTimeStamps(self, sliderValue):
		"""
		Update the time stamps displayed on two sides of the slider
		"""
		portion = float(sliderValue) * 0.01
		elapsedTime = round(self.videoLength * portion)
		self.timeStamp1.set(datetime.timedelta(seconds = elapsedTime))
		self.timeStamp2.set(datetime.timedelta(seconds = self.videoLength - elapsedTime))



	def setTimeLine(self, timeConfig):
		#reset the timeline
		self.numFrame = timeConfig["nframe"]
		self.videoLength = timeConfig["duration"]
		self.slider.configure(state=ACTIVE)
		self.sliderTick = round(100 / self.videoLength, 2)
		self.timeStamp1.set("00:00:00")
		self.timeStamp2.set(datetime.timedelta(seconds=self.videoLength))

		self.slider.configure(state=ACTIVE)
		self.slider.configure(resolution=self.sliderTick)
		self.slider.set(0)
		self.slider.configure(state=DISABLED)
		


	def setupMovie(self):
		"""Setup RTSP connection with server."""
		self.rtspSeq = 0
		self.numRtpPacket = 0   #number of RTP packets received in a session

		#open RTSP soclet annd connect to server
		self.connectToServer()

		#send SETUP RTSP request
		self.sendRtspRequest(self.SETUP)

		reply = self.recvRtspReply()

		if reply["Status"] != 200:
			#an error occured
			print("SETUP failed!")
			return

		#get the session id from server
		self.sessionId = int(reply["Session"])

		#get the number of frames and duration of the video
		self.setTimeLine(reply["body"])

		#create a RTP socket to start receiving RTP packets
		self.openRtpPort()
		
		#start clock thread
		self.clockThread = threading.Thread(target=self.clock)
		self.clockThread.start()

		#change the client's state to READY
		self.state = self.READY



	def getVideoList(self):
		"""Get the video list from server and display it"""
		if self.state == self.INIT:
			self.setupMovie()

		
		self.sendRtspRequest(self.LIST)

		reply = self.recvRtspReply()

		if reply["Status"] != 200:
			print("LIST failed!")
			return

		self.videoList = reply['body']['list']


		for i in range(3):
			if i < len(self.videoList):
				videoName = self.videoList[i]
				self.listButtons[i].configure(
					text = videoName,
					command= lambda x=videoName: self.switchMovie(x)
				)
				if videoName == self.fileName:
					self.listButtons[i].configure(state=DISABLED, background="#cccccc", bd=0)
				else:
					self.listButtons[i].configure(state=NORMAL, background="#f0f0f0", bd=2)

				self.listButtons[i].grid(row=(2+i), column=0, padx=(40,10))
			else:
				self.listButtons[i].grid_remove()



	def exitClient(self):
		"""Teardown button handler."""
		if self.state != self.INIT:
			#save sessionID
			sessionId = self.sessionId

			#change client's state to INIT
			self.state = self.INIT

			#send TEARDOWN RTSP requuest
			self.sendRtspRequest(self.TEARDOWN)

			#receive server's RTSP reply
			reply = self.recvRtspReply()
			
			if reply["Status"] != 200:
				#an error occurred
				print("TEARDOWN failed!")
				return

			#close the RTP socket
			self.rtpSocket.close()

			#close RTSP socket => end session here
			self.rtspSocket.close()

			#stop the clock thread
			if self.clockThread != None:
				#unlock clock thread (in case it is paused)
				self.clockEvent.set()
				sleep(1)

			self.slider.configure(state=DISABLED)
			self.clockEvent.clear()

			#diplay some logging
			print("============= SESSION LOG =============")
			print(f"Session ID: {sessionId}")
			print(f"Number of RTP packets received: {self.numRtpPacket}\n")

			

	def pauseMovie(self):
		"""Pause button handler."""
		if self.state == self.PLAYING:
			#change the client's state to READY
			self.state = self.READY
			
			#send PAUSE RTSP request
			self.sendRtspRequest(self.PAUSE)

			reply = self.recvRtspReply()

			if reply["Status"] != 200:
				#an error occurred
				print("PAUSE failed!")

			#pause the clock thread
			self.slider.configure(state=DISABLED)
			self.clockEvent.clear()



	def playMovie(self):
		"""Play button handler."""
		if self.state == self.INIT or self.state == self.PENDING:
			#automatically set up when user presses Play button (if needed)
			self.setupMovie()
			

		if self.state == self.READY:
			#send the PLAY RTSP request
			self.sendRtspRequest(self.PLAY)

			reply = self.recvRtspReply()

			if reply["Status"] != 200:
				#an error occurred
				print("PLAY failed!")
				return

			self.state = self.PLAYING

			#start receiving RTP packets
			self.worker = threading.Thread(target=self.listenRtp)
			self.worker.start()

			#start the clock
			self.slider.configure(state=ACTIVE)
			self.clockEvent.set()



	def forwardMovie(self, event):
		"""Forward the video to a specific frame"""
		if self.slider["state"] == DISABLED:
			return

		portion = self.slider.get() * 0.01
		frameNbr = round(self.numFrame * portion)
		frameNbr = frameNbr if frameNbr > 0 else 1

		self.clockEvent.clear()
		self.slider.configure(state=DISABLED)
		self.state = self.READY

		self.sendRtspRequest(self.FORWARD, frameNbr=frameNbr)

		reply = self.recvRtspReply()

		if reply["Status"] != 200:
			print("FORWARD failed!")
			return
	
		self.worker = threading.Thread(target=self.listenRtp)
		self.worker.start()

		self.state = self.PLAYING
		self.slider.configure(state=ACTIVE)
		self.clockEvent.set()



	def describeStream(self):
		if self.state == self.INIT:
			self.setupMovie()

		self.sendRtspRequest(self.DESCRIBE)

		reply = self.recvRtspReply()

		if reply["Status"] != 200:
			print("DESCRIBE failed!")
			return

		streams = reply['body']['streams']
		encoding = reply['body']['encoding']

		print("============ SESSION DESCRIBE ============")
		print(f"Streams: {streams}")
		print(f"Encoding: {encoding}")



	def switchMovie(self, fileName):
		"""Switch to a new movie"""

		#stop the clock
		self.slider.configure(state=DISABLED)
		self.clockEvent.clear()

		self.sendRtspRequest(self.SWITCH, fileName=fileName)

		reply = self.recvRtspReply()

		if reply['Status'] != 200:
			print('SWITCH failed!')
			return
		
		self.setTimeLine(reply["body"])

		#update the UI
		for i in range(3):
			if self.listButtons[i]["text"] == fileName:
				self.listButtons[i].configure(state=DISABLED, background="#cccccc", bd=0)
			elif self.listButtons[i]["text"] == self.fileName:
				self.listButtons[i].configure(state=NORMAL, background="#f0f0f0", bd=2)

		self.label.configure(image='')

		self.fileName = fileName
		self.state = self.PENDING



	def listenRtp(self):		
		"""Listen for RTP packets."""
		while True:
			try:
				data = self.rtpSocket.recvfrom(65536)[0]
			except Exception as e:
				#socket error or timeout => PAUSE or TEARDOWN command issued
				break

			#de-serialize the RTP packet
			packet = RtpPacket()
			packet.decode(data)

			self.numRtpPacket += 1
			self.frameNbr = packet.seqNum()

			#write the frame to a file
			imageFile = self.writeFrame(packet.getPayload(), self.frameNbr)

			#display the frame
			self.updateMovie(imageFile)



	def writeFrame(self, data, frameNbr):
		"""Write the received frame to a temp image file. Return the image file."""
		imageFileName = CACHE_FILE_NAME + str(frameNbr) + CACHE_FILE_EXT
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

	

	def sendRtspRequest(self, requestCode, frameNbr=None, fileName=None):
		"""Send RTSP request to the server."""	
		#-------------
		# TO COMPLETE
		#-------------
		request = ""

		if requestCode == self.SETUP:
			request = f"SETUP {self.fileName} RTSP/1.0\nCSeq: {self.rtspSeq}\nTransport: RTP/UDP; client_port= {self.rtpPort}"

		elif requestCode == self.PLAY:
			request = f"PLAY {self.fileName} RTSP/1.0\nCSeq: {self.rtspSeq}\nSession: {self.sessionId}"

		elif requestCode == self.FORWARD:
			request = f"FORWARD {self.fileName} RTSP/1.0\nCSeq: {self.rtspSeq}\nSession: {self.sessionId}\nFrame: {frameNbr}"

		elif requestCode == self.PAUSE:
			request = f"PAUSE {self.fileName} RTSP/1.0\nCSeq: {self.rtspSeq}\nSession: {self.sessionId}"

		elif requestCode == self.TEARDOWN:
			request = f"TEARDOWN {self.fileName} RTSP/1.0\nCSeq: {self.rtspSeq}\nSession: {self.sessionId}"

		elif requestCode == self.LIST:
			request = f"LIST RTSP/1.0\nCSeq: {self.rtspSeq}\nSession: {self.sessionId}"

		elif requestCode == self.DESCRIBE:
			request = f"DESCRIBE RTSP/1.0\nCSeq: {self.rtspSeq}\nSession: {self.sessionId}"

		elif requestCode == self.SWITCH:
			print(fileName)
			request = f"SWITCH {fileName} RTSP/1.0\nCSeq: {self.rtspSeq}\nSession: {self.sessionId}"


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
		reply["Status"] = int(lines[0].split(" ")[1])

		if reply["Status"] == 200:
			#extract headers
			for line in lines[1:3]:
				key, value = line.split(": ")
				reply[key] = value

			if len(lines) > 3:
				#extract the body
				reply['body'] = json.loads(lines[3])


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


		

