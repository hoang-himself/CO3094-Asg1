class VideoStream:
	def __init__(self, filename):
		self.filename = filename

		try:
			self.file = open(filename, 'rb')
		except:
			raise IOError

		self.frameNum = 0
		self.numFrame = int(self.file.read(10).decode())   #first 10 bytes contain the number of frames


	def nextFrame(self):
		"""Get next frame."""
		data = self.file.read(5) 	# Get the framelength from the first 5 bytes

		if data: 
			framelength = int(data)
							
			# Read the current frame
			data = self.file.read(framelength)
			self.frameNum += 1
			
		return data


	def moveTo(self, frameNum):
		if frameNum > self.numFrame or frameNum <= 0:
			return

		self.file.seek(10)
		self.frameNum = frameNum - 1

		for _ in range(self.frameNum):
			offset = int(self.file.read(5).decode())
			self.file.seek(offset, 1)


	def frameNbr(self):
		"""Get frame number."""
		return self.frameNum


	def getNumFrame(self):
		"""total number of frames in the video"""
		return self.numFrame

	
	