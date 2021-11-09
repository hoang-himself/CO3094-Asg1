from time import time


HEADER_SIZE = 12     


class RtpPacket:	
	header = bytearray(HEADER_SIZE)
	
	def __init__(self):
		pass
		
	def encode(self, version, padding, extension, cc, seqnum, marker, pt, ssrc, payload):
		"""Encode the RTP packet with header fields and payload."""
		timestamp = int(time())
		self.header = bytearray(HEADER_SIZE)
	
		#first 4 bytes
		self.header[0] =  (version << 6)   	#set the first 2 bits of byte 0 (version)
		self.header[0] |= (padding << 5)   	#set the 3rd bit of byte 0 (padding)
		self.header[0] |= (extension << 4) 	#set the 4th bit of byte 0 (extension)
		self.header[0] |= cc               	#set the last 4 bits of byte 0 (contributing sources)

		self.header[1] = (marker << 7)    	#set the first bit of byte 1 (marker)
		self.header[1] |= pt					#set the last 7 bits of byte 1 (payload type)

		self.header[2] = (seqnum >> 8)       #the upper byte of sequence number
		self.header[3] = (seqnum & 0xff)		#the lower byte of sequence number


		#timestamp field (4 bytes)
		self.header[4] = (timestamp >> 24)			
		self.header[5] = (timestamp >> 16) & 0xff
		self.header[6] = (timestamp >> 8) & 0xff
		self.header[7] = timestamp & 0xff


		#source identifier field (4 bytes)
		self.header[8] = (ssrc >> 24)				
		self.header[9] = (ssrc >> 16) & 0xff
		self.header[10] = (ssrc >> 8) & 0xff
		self.header[11] = ssrc & 0xff


		#get the payload
		self.payload = payload

		
	def decode(self, byteStream):
		"""Decode the RTP packet."""
		self.header = bytearray(byteStream[:HEADER_SIZE])
		self.payload = byteStream[HEADER_SIZE:]
	
	def version(self):
		"""Return RTP version."""
		return int(self.header[0] >> 6)
	
	def seqNum(self):
		"""Return sequence (frame) number."""
		seqNum = self.header[2] << 8 | self.header[3]
		return int(seqNum)
	
	def timestamp(self):
		"""Return timestamp."""
		timestamp = self.header[4] << 24 | self.header[5] << 16 | self.header[6] << 8 | self.header[7]
		return int(timestamp)
	
	def payloadType(self):
		"""Return payload type."""
		pt = self.header[1] & 127
		return int(pt)
	
	def getPayload(self):
		"""Return payload."""
		return self.payload
		
	def getPacket(self):   #convert the RTPPacket object to a byte stream
		"""Return RTP packet."""
		return self.header + self.payload