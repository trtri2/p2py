from bencode import *
from torrent import *
from protocol import *

# FIXME: would p be confusing for peer?
from protocol import *
import asyncio
import json

class TrackerServer:                              
    #torrent metadata
    def __init__(self):
        self.nextTorrentId = 0 
        self.torrent = {}              #the torrent list (dictionary), defined by its unique torrentID

    def handleRequest(self, req):
        opc = req.get(OPC)
        response = {OPC: opc}
        
        if opc == OPT_GET_LIST:
            torrent_list = self.getTorrentDict()
            if torrent_list:
                response.update({ TORRENT_LIST: self.getTorrentDict() })
                response.update({ RET: RET_SUCCESS })
            else:
                response.update({ RET: RET_FAIL })

        elif opc == OPT_GET_TORRENT:
            torrent_obj = self.getTorrentObject(req)
            if torrent_obj:
                response.update({ TORRENT: torrent_obj })
                response.update({ RET: RET_SUCCESS })
            else:
                response.update({ RET: RET_FAIL })

        elif opc == OPT_START_SEED:
            response.update({ RET: self.updatePeerStatus(req) })

        elif opc == OPT_STOP_SEED:
            response.update({ RET: self.updateStopSeed(req) })

        elif opc == OPT_UPLOAD_FILE: #upload new file --> create new torrent object
            response.update({ RET: self.addNewFile(req) })

        else: #invalid opc
            response.update({ RET: RET_FAIL })

        return response
    
    def getTorrentDict(self) -> dict():                   #res opcode=1
        """
        Returns a dictionary of available torrents stored in the tracker
        """
        return self.torrent
    
    def getTorrentObject(self, req: dict) -> dict():      #res opcode=2
        """
        Returns the specific torrent dictionary from the torrent id
        """
        responseDict = {}
        if req[TID] not in self.torrent:  #torrent object does not exist in list
            return responseDict   

        torrentObj = self.torrent[req[TID]]
        # we must deconstruct the torrent object since we can't send an object
        # for now we'll just say you can only seed once you are done leeching.
        responseDict[TORRENT] = { 
                                  TID: torrentObj.tid,
                                  FILE_NAME: torrentObj.filename, 
                                  TOTAL_PIECES: torrentObj.pieces, 
                                  SEEDER_LIST: torrentObj.seeders,
                                  LEECHER_LIST: torrentObj.leechers
                                }                 
        self.torrent[ req[TID] ].addLeecher(req[PID], req[IP], req[PORT])  
        return responseDict

    def updatePeerStatus(self, req:dict) -> int:
        """
        Adds peer to the torrent's peer seeding list
        """
        if req[TID] not in self.torrent:
            return RET_FAIL

        self.torrent[ req[TID] ].addSeeder(req[PID], req[IP], req[PORT])
        # for now we'll just say that you can only seed once you are done leeching
        self.torrent[ req[TID]].removeLeecher(req[PID], req[IP], req[PORT])
        return RET_SUCCESS

    def updateStopSeed(self, req: dict) -> int: 
        if req[TID] not in self.torrent:
            return RET_FAIL
        
        peer = req[PID]
        if peer:
            self.torrent[req[TID]].removePeer(req[PID])
        else:
            return RET_FAIL
        
        return RET_SUCCESS

    def addNewFile(self, req: dict) -> int:
        """
        Creates a torrent from the given filename and pieces and adds it to the torrent list
        """
        newTorrent = Torrent(self.nextTorrentId, req[FILE_NAME], req[TOTAL_PIECES])        #create the torrent object
        newTorrent.addSeeder(req[PID], req[IP], req[PORT])                      #add peer the seeder into torrent object   
        self.torrent[self.nextTorrentId] = newTorrent    #insert into torrent dictionary
        self.nextTorrentId+=1
        # print(f"That piece: {req['DEBUG_PIECE_1']!r}")
        return RET_SUCCESS
    
    async def receiveRequest(self, reader, writer):
        '''
            Take in the client request
            It will call handleRequest -> give it a response object {"OPT": __, RET: __, "payload": __ }
            receiveRequest will send this ---^ response object
        '''
        # TODO: 200 is the current constant, what is max req request size?
        try:
            data = await reader.read(600)
        
            cliRequest = json.loads(data.decode())
            addr = writer.get_extra_info('peername')

            print(f"\n[TRACKER] Debug received {cliRequest!r} from {addr!r}.")
            
            response = self.handleRequest(cliRequest)

            # Send payload response to client
            payload = json.dumps(response)
            print("[TRACKER] Debug send payload:", payload)
            writer.write(payload.encode())
            
            await writer.drain()
            print("[TRACKER] Closing the connection for", addr)
        except:
            print("[TRACKER] Peer", writer.get_extra_info('peername'), "has disconnected.")

        writer.close()

async def main():
    ip = "127.0.0.1"
    port = 8888
    
    t = TrackerServer()
    server = await asyncio.start_server(t.receiveRequest, ip, port)
    addr = server.sockets[0].getsockname()
    print(f'[TRACKER] Serving on {addr}')

    async with server:
        await server.serve_forever()

asyncio.run(main())