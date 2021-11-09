import sys, socket, signal, os


from ServerWorker import ServerWorker


class Server:	
	workers = []	#queue of workers


	def main(self):
		signal.signal(signal.SIGINT, self.exitHandler)

		try:
			SERVER_PORT = int(sys.argv[1])
		except:
			print("[Usage: Server.py Server_port]\n")


		rtspSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		rtspSocket.bind(('', SERVER_PORT))
		rtspSocket.listen(5)        


		# Receive client info (address,port) through RTSP/TCP session
		while True:
			clientInfo = {}
			clientInfo['rtspSocket'] = rtspSocket.accept()

			#each client is handled by a seperate worker
			worker = ServerWorker(clientInfo)
			worker.run()
			self.workers.append(worker)



	def exitHandler(self):
		'''
		Called when pressing Ctrl-C to shutdown server
		'''
		print("Shutting down server ...")

		#terminate all worker threads
		for worker in self.workers:
			worker.terminate()

		os._exit()

		

if __name__ == "__main__":
	(Server()).main()


