"""
Provides Client's functionalities and actions. See client_handler which is the main entry point for user interaction handling
"""
from protocol import *
import file_handler
import json
import asyncio
import sys
import uuid
from socket import *

class Client:
    def __init__(self, src_ip, src_port):
        self.peer_id = self.createPeerID()
        self.src_ip = src_ip
        self.src_port = src_port

        # Peer States
        self.peer_choked = True
        self.peer_interested = False
        self.peer_am_seeding = False
        self.peer_am_leeching = False

        # List of seeders & piece buffer associated to the current download 
        self.seeders_list = dict()
        self.piece_buffer = PieceBuffer()


########### CONNECTION HANDLING ###########

    async def connectToTracker(self, ip, port):
        if ip == None and port == None:
            # Use default IP and port
            ip = "127.0.0.1"
            port = "8888"
    
        try:
            print("Connecting to " + ip + ":" + port + " ...")
            reader, writer = await asyncio.open_connection(ip, int(port))
            print("Connected as peer: " + self.src_ip + ":" + self.src_port + ".")
            return reader, writer

        except ConnectionError:
            print("Connection Error: unable to connect to tracker.")
            sys.exit(-1) # different exit number can be used, eg) errno library

    async def connectToPeer(self, ip, port, payload):
        """
        This function handles both sending the payload request, and receiving the expected response
        """
        try:
            print("Connecting to seeder:" + ip + ":" + port + " ...")
            reader, writer = await asyncio.open_connection(ip, int(port))
            print("Connected as leecher: " + self.src_ip + ":" + self.src_port + ".")

        except ConnectionError:
            print("Connection Error: unable to connect to tracker.")
            sys.exit(-1) # different exit number can be used, eg) errno library

        await self.send(writer, payload)
        await self.receive(reader)
        writer.close()

    async def receive(self, reader):
        """
        Handle incoming requests and decode to the JSON object.
        Pass the JSON object to handleRequest() that will handle the request appropriately.
        """
        data = await reader.read(200)
        payload = json.loads(data.decode())
        print(f'[PEER] Received decoded message: {payload!r}')
        # TODO: handle OPC to determine whether its SERVER or PEER response using OPC 
        # self.handleServerResponse(payload)
        return

    async def send(self, writer, payload:dict):
        """
        Encode the payload to an encoded JSON object and send to the appropriate client/server
        ? Do we automatically know who to send it to ?
        """
        jsonPayload = json.dumps(payload)
        print("[PEER] Sending encoded request message:", (jsonPayload))
        writer.write(jsonPayload.encode())

    

########### REQUEST & RESPONSE HANDLING ###########

    def handleServerResponse(self, response) -> int:
        """
        Handle the response from a server, presumably a python dict has been loaded from the JSON object.
        Note: The delegation must be handled elsewhere (i.e. in receive()) to determine whether its SERVER or PEER response using OPC 
        """
        ret = response[RET]
        opc = response[OPC]

        if ret == RET_FAIL or ret != RET_SUCCESS:
            return -1
        
        if opc == OPT_GET_LIST:
            torrent_list = response[TORRENT_LIST]
            print("todo: print the results?")
        elif opc == OPT_GET_TORRENT:
            torrent = response[TORRENT]
            self.seeders_list = response[PEER_LIST]
            self.piece_buffer.setBuffer(torrent.TOTAL_PIECES)
            
            #we immediately start the downloading process upon receiving the torrent object
            self.downloadFile(torrent.pieces, torrent.filename)
            print("DEBUG: downloading torrent : ", torrent.filename)
        elif opc == OPT_START_SEED or opc == OPT_UPLOAD_FILE:
            self.peer_am_seeding = True
            print("todo: allow seeding... the user should not be able to download other files?")
        elif opc == OPT_STOP_SEED:
            self.peer_am_seeding = False
            print("todo: allow the user to regain control?")

        return 1

    def createServerRequest(self, opc:int, torrent_id=None, filename=None) -> dict:
        """
        Called from client_handler.py to create the appropriate server request given the op code
        Returns a dictionary of our payload.
        """
        payload = {OPC:opc, IP:self.src_ip, PORT:self.src_port, PID:self.peer_id}
        # get list of torrents is default payload as above

        if opc == OPT_GET_TORRENT or opc == OPT_START_SEED or opc == OPT_STOP_SEED:
            payload[TID] = torrent_id
        elif opc == OPT_UPLOAD_FILE:
            numPieces = self.uploadFile(filename)
            payload[FILE_NAME] = filename
            payload[TOTAL_PIECES] = numPieces

            #DEBUG send a piece to tracker
            # payload["DEBUG_PIECE_1"] = (self.piece_buffer.getBuffer()[0])
            # print(self.piece_buffer.getBuffer()[0])

        return payload

    def handlePeerResponse(self, response):
        """
        Handle the response from a peer.
        """
        ret = response[RET]
        opc = response[OPC]

        if ret == RET_FAIL or ret != RET_SUCCESS:
            return -1
        
        if opc == OPT_GET_PEERS:
            peers_list = response[PEER_LIST]
            print("TODO: printing peers_list.. ", peers_list)
        elif opc == OPT_GET_PIECE:
            data = response[PIECE_DATA]
            idx = response[PIECE_IDX]
            newPiece = Piece(idx, data)
            self.piece_buffer.addData(newPiece)

    def handlePeerRequest(self, request) -> dict():
        """
        Handle the incoming request (this applies to peers only). Returns a response dictionary object.
        """
        opc = request[OPC]
        response = {OPC: opc, IP:self.src_ip, PORT:self.src_ip}

        if opc == OPT_STATUS_INTERESTED:
            print('todo')
        elif opc == OPT_STATUS_UNINTERESTED:
            print('todo')
        elif opc == OPT_STATUS_CHOKED:
            print('todo')
        elif opc == OPT_STATUS_UNCHOKED:
            print('todo')
        elif opc == OPT_GET_PEERS:
            response[PEER_LIST] = self.seeders_list
            response[RET] = RET_SUCCESS
        elif opc == OPT_GET_PIECE:
            piece_idx = request[PIECE_IDX]
            if self.piece_buffer.checkIfHavePiece(piece_idx):
                response[PIECE_DATA] = self.piece_buffer.getData(piece_idx)
                response[PIECE_IDX] = request[PIECE_IDX]
                response[RET] = RET_SUCCESS
            else:
                response[RET] = RET_FAIL
        return response
        
    def createPeerRequest(self, opc:int, piece_idx=None) -> dict:
        """
        Create the appropriate peer request.
        """
        payload = {OPC:opc, IP:self.src_ip, PORT:self.src_ip}

        if opc == OPT_GET_PIECE:
            payload[PIECE_IDX] = piece_idx
        
        return payload


########### HELPER FUNCTIONS ###########

    # This may need to be async here..
    def simplePeerSelection(self, numPieces:int):
        """
        A simple peer selection that downloads and entire file from a single peer.
        """

        # assuming here peer_list is a dictionary. Just grab the first one to be the seeder.
        # this code requires py 3.6+
        pid = next(iter(self.seeders_list))
        initialPeer_ip = self.seeders_list[pid][IP]
        initialPeer_port = self.seeders_list[pid][PORT]
        
        for idx in range(numPieces):
            request = self.createPeerRequest(OPT_GET_PIECE, idx)
            self.connectToPeer(initialPeer_ip, initialPeer_port, request)
        
    def downloadFile(self, numPieces:int, filename:str):
        """
        Method for starting the download of a file by calling the peer selection method to download pieces
        Once done, output it to the output directory with peer_id appended to the filename.
        """
        self.simplePeerSelection(numPieces)
        while not self.piece_buffer.checkIfHaveAllPieces:
            pass
        
        pieces2file = []
        outputDir = './output' + peer_id + '_' + filename
        for i in range(self.piece_buffer.getSize):
            pieces2file.append(self.piece_buffer.getData())

        try:
            file_handler.decodeToFile(pieces2file, outputDir)
            print("Successfully downloaded file: ", outputDir)
        except:
            print("Exception occured in downloadFile() with filename:", filename)
        

    def uploadFile(self, filename: str) -> int:
        """
        Called when the user begins to be the initial seeder (upload a file). The piecebuffer will be
        populated and initialized.
        Returns the number of pieces in the created piece buffer.
        """
        
        # DEBUGGING:
        filename = 'sample.txt'
        pieces = []
        numPieces = 0
        try:
            pieces, numPieces = file_handler.encodeToBytes(filename)
        except:
            print("Exception occured in uploadFile() with filename:", filename)

        # Set the buffer size and add the file's data to the buffer.
        self.piece_buffer.setBuffer(numPieces)

        for idx in range(len(pieces)):
            currPiece = Piece(idx, pieces[idx])
            self.piece_buffer.addData(currPiece)      

        return numPieces

    def createPeerID(self) -> str:
        """
        Ideally, create a unique peer ID.
        uuid4 > uuid1 as it gives privacy (no MAC address)
        """
        return str(uuid.uuid4())
        
class Piece:
    """
    Files are split into pieces 
    index -> piece's index in the expected buffer

    """
    def __init__(self, index: int, data):
        self.index = index
        self.data = data

class PieceBuffer:
    """
    A piece manager that handles the current piece buffer for the requested file
    """

    def __init__(self):
        self.__buffer = []
        self.__size = 0
        self.__havePieces = []
    
    def getBuffer(self):
        return self.__buffer

    def setBuffer(self, length: int):
        self.__buffer = [0] * length
        self.__size = length
        self.__havePieces = [False] * length

    def addData(self, piece: Piece) -> int:
        idx = piece.index
        data = piece.data
        if idx < 0 or idx >= self.__size:
            return -1
        else:
            self.__buffer[idx] = data
            self.__havePieces[idx] = True
            return 1

    def getData(self, idx: int):
        """
        Returns the piece bytes at the specified index.
        """
        if idx < 0 or idx >= self.__size or self.__buffer[idx] == 0:
            return -1
        else:
            return self.__buffer[idx]

    def getSize(self) -> int:
        return self.__size

    def getMissingPieces(self) -> [int]:
        missingPieces = []
        for idx, pce in enumerate(self.__havePieces):
            if not pce:
                missingPieces.append(idx)
        return missingPieces
    
    def checkIfHavePiece(self, idx:int) -> bool:
        return self.__havePieces[idx]
    
    def checkIfHaveAllPieces(self) -> bool:
        for pce in self.__havePieces:
            if not pce:
                return False
        return True
    


    