####################################################
# Ninja Ripper 2 output file (.nr) parser-reader
####################################################

# Starting from NR2.0.15 at least NRIP version 3 supported
# NRIPVER==1 NRIPVER==2 is DEPRECATED

import os
import struct
import math


# Supported nr.ver=3
def _kVersion():
    return 3


class VaType:
    Float  = 0
    Uint32 = 1
    Uint16 = 2
    Uint8  = 3
    Sint32 = 4
    Sint16 = 5
    Sint8  = 6
    Float64= 7
    Uint64 = 8
    Sint64 = 9


# One enum for PostVS and PreVS
#  PostVS is always 'List'
#  PreVS indexes is converted from strips/lists to lists
class PrimitiveTopology:
    TriangleList = 1
    PointList    = 2
    LineList     = 3


class TlvTypeId:
    Dword  = 1
    String = 2


class ShaderStage:
    PreVs = 1
    Vs    = 2
    DsGs  = 3


###############################################################################

def _kMagic():
    return 0x5049524E

def tagVERT():
    return createTag('V', 'E', 'R', 'T')

def tagINDX():
    return createTag('I', 'N', 'D', 'X')

def tagVATR():
    return createTag('V', 'A', 'T', 'R')

def tagTXTR():
    return createTag('T', 'X', 'T', 'R')

def tagGEOM():
    return createTag('G', 'E', 'O', 'M')

def tagPROP():
    return createTag('P', 'R', 'O', 'P')

def tagSHD1():
    return createTag('S', 'H', 'D', '1')


def createTag(c0, c1, c2, c3):
    return (ord(c3) << 24) | (ord(c2) << 16) | (ord(c1) << 8) | ord(c0)


def tagToString(tag):
    return ("{:c}{:c}{:c}{:c}".format( (tag & 0xff), ((tag>>8) & 0xff), ((tag>>16) & 0xff), ((tag>>24) & 0xff) ))

def getNrMagic():
    return _kMagic()


# nr - file parser
class NRFile(object):
    def __kChunkFileHeaderSize(self):
        return 12

    def __init__(self):
        self.__errorStr = ""
        self.__ripFile = None
        self.__chunksMap = {}
        self.__fileSize = 0

    def getFileSize(self):
        return self.__fileSize

    def getErrorString(self):
        return self.__errorStr

    def seek(self, offs):
        self.__ripFile.seek(offs, 0)

    def readBytes(self, sizeInBytes):
        v = self.__ripFile.read(sizeInBytes)
        if not v:
            return None
        return v

    def readU64(self):
        v = self.__ripFile.read(8)
        if not v:
            return None
        return struct.unpack('Q', v)[0]

    def readU32(self):
        v = self.__ripFile.read(4)
        if not v:
            return None
        return struct.unpack('I', v)[0]

    def readU16(self):
        v = self.__ripFile.read(2)
        if not v:
            return None
        return struct.unpack('H', v)[0]

    def readU8(self):
        v = self.__ripFile.read(1)
        if not v:
            return None
        return struct.unpack('B', v)[0]

    def readString(self):
        str = b''
        while True:
            c = self.__ripFile.read(1)
            if not c:
                return None

            if c == b'\0' or c == b'':
                return str.decode()
            else:
                str = str + c

    def getChunkMap(self):
        return self.__chunksMap

    def getChunk(self, tag, idx):
        arr = self.__chunksMap.get(tag)
        if arr:
            if idx < len(arr):
                return arr[idx]
        return None

    def getNrVersion(self):
        return self.version

    def parse(self, fileName):
        res = False

        try:
            self.__ripFile = open(fileName, "rb")
            self.__ripFile.seek(0, os.SEEK_END)
            self.__fileSize = self.__ripFile.tell()
            self.__ripFile.seek(0, os.SEEK_SET)

            magic = self.readU32()
            if magic != _kMagic():
                raise Exception("NRIP magic not found")

            self.version = self.readU32()
            if 1 == self.version:
                raise Exception("Deprecated NR version. Use importer from NR 2.0.3")
            if 2 == self.version:
                raise Exception("Deprecated NR version. Use importer from NR 2.0.4")
            #if _kVersion() < self.version:
            #    raise Exception("Ninja Ripper Version={} > Importer Version={}. Update import scripts.".format(self.version, _kVersion()))



            reserved0 = self.readU32()
            reserved1 = self.readU32()

            while (True):
                chunk = Chunk()

                curp = self.__ripFile.tell()
                if curp >= self.__fileSize:
                    break

                chunk.rawSize  = self.readU32() # chunk file header(12) + chunk header+data size
                chunk.tag      = self.readU32() # chunk tag
                chunk.idx      = self.readU32() # chunk index
                chunk.rawOffs  = curp
                chunk.headerOffs = chunk.rawOffs + self.__kChunkFileHeaderSize() # Helper

                self.__ripFile.seek(curp + chunk.rawSize, 0)

                arr = self.__chunksMap.get(chunk.tag)
                if not arr:
                    arr = []
                arr.append(chunk)
                tagIdx = len(arr) - 1
                if tagIdx != chunk.idx:
                    raise Exception("Chunk index error")

                self.__chunksMap[chunk.tag] = arr
            res = True
        except Exception as e:
            self.__errorStr = ("NR-file parsing exception: {}").format(str(e))
        return res


    # TriangleList/LineList/PointList
    def getMeshCount(self):
        arr = self.__chunksMap.get(tagGEOM())
        if arr:
            return len(arr)
        return 0

    def getMesh(self, idx):
        arr = self.__chunksMap.get(tagGEOM())
        if arr:
            if idx < len(arr):
                g = Geometry(self, arr[idx])
                return g
        return None

    def getChunkCount(self, tag):
        arr = self.__chunksMap.get(tag)
        if arr:
            return len(arr)
        return 0

#-------------------------------------------------
# Sub classes
#-------------------------------------------------
class Chunk(object):
    def __init__(self):
        self.tag      = 0
        self.idx      = 0 # Tag index
        self.rawOffs  = 0 # Offset of raw chunk header
        self.rawSize  = 0 # ChunkFileHeader + ChunkHeader + ChunkData
        self.headerOffs = 0


# Point/Line/Triangle geometry
class Geometry(object):
    def __init__(self, nr, chunk):
        self.__nr = nr
        self.__chunksMap = {}

        nr.seek(chunk.headerOffs)

        self.__flags = nr.readU32()   # PrimitiveTopology+ShaderStage
        geomEntriesCount = nr.readU32()
        self.drawCallId  = nr.readU32()
        self.instanceCount = nr.readU32()
        self.ripId  = nr.readU32()
        self.group0Id = nr.readU32()
        self.group1Id = nr.readU32()
        self.frameId  = nr.readU32()

        for idx in range(0, geomEntriesCount):
            tag  = nr.readU32()
            idx  = nr.readU32()

            arr = self.__chunksMap.get(tag)
            if not arr:
                arr = []

            chunk = self.__nr.getChunk(tag, idx)
            arr.append(chunk)

            self.__chunksMap[tag] = arr

    def __getChunk(self, tag):
        arr = self.__chunksMap.get(tag)
        if arr:
            return arr[0]
        return None

    def getGroup0Id(self):
        return self.group0Id

    def getGroup1Id(self):
        return self.group1Id

    def getFrameId(self):
        return self.frameId
        
    # Return: PrimitiveTopology
    def getPrimitiveTopology(self):
        return (self.__flags & 3)


    # Return: Mesh shader stage
    def getShaderStage(self):
        return ((self.__flags & 0x1C) >> 2)


    def getIndexes(self, idx):
        for chunkArr in self.__chunksMap.values():
            if chunkArr[0].tag == tagINDX():
                if idx < len(chunkArr):
                    return Indexes(self.__nr, chunkArr[idx])
                return None
        return None
        
    def getVertexAttributes(self, idx):
        for chunkArr in self.__chunksMap.values():
            if chunkArr[0].tag == tagVATR():
                if idx < len(chunkArr):
                    return VertexAttributes(self.__nr, chunkArr[idx])
                return None
        return None
        
    def getTextures(self):
        chunk = self.__getChunk(tagTXTR())
        if chunk:
            return Textures(self.__nr, chunk)
        return None


    def getShaders(self):
        chunk = self.__getChunk(tagSHD1())
        if chunk:
            return Shaders(self.__nr, chunk)
        return None
        
        
    def getAllProperties(self):
        res = []
        for chunkArr in self.__chunksMap.values():
            if chunkArr[0].tag == tagPROP():
                for chunk in chunkArr:
                    prop = Properties(self.__nr, chunk)
                    res.append(prop)
        return res

    def getProperties(self, propTag):
        props = self.getAllProperties()
        for p in props:
            if p.tag == propTag:
                return p
        return None

    # 0 - base vert
    # 1 - extra     (0/1-pre/post (post/pre))
    def getVertexes(self, idx):
        for chunkArr in self.__chunksMap.values():
            if chunkArr[0].tag == tagVERT():
                if idx < len(chunkArr):
                    return Vertexes(self.__nr, chunkArr[idx])
                return None
        return None


class Indexes(object):
    def __INDX_headerSize(self):
      return 8

    def __init__(self, nr, chunk):
        self.__nr = nr
        self.__indexCount = 0
        self.__topology = 0
        self.__INDX_chunk = chunk

        nr.seek(chunk.headerOffs)
        self.__indexCount = nr.readU32()
        self.__topology   = nr.readU32()

    def getIndexCount(self):
        return self.__indexCount
        
    #def getPrimitiveTopology(self):
    #    return self.__topology

    # Read all indexes to buffer
    def read(self):
        # IndexCount * sizeof(uint32_t)
        self.__nr.seek(self.__INDX_chunk.headerOffs + self.__INDX_headerSize())
        return self.__nr.readBytes(self.__indexCount * 4)


# Single vertex attribute
class VertexAttribute(object):
    def __init__(self, nr):
        self.semantic  = nr.readString()
        self.semanticIdx = nr.readU32()    # Alway == 0 (Not set by NR)
        self.vaType    = nr.readU32()
        self.offs      = nr.readU32()
        self.compCount = nr.readU32()
        self.semIdx    = 0                 # Calculated by importer

    def getFormat(self):
        # '4h' means exactly the same as 'hhhh'
        if VaType.Float == self.vaType:
            return "{}f".format(self.compCount)
        elif VaType.Uint32 == self.vaType:
            return "{}L".format(self.compCount)
        elif VaType.Uint16 == self.vaType:
            return "{}H".format(self.compCount)
        elif VaType.Uint8 == self.vaType:
            return "{}B".format(self.compCount)
        elif VaType.Sint32 == self.vaType:
            return "{}l".format(self.compCount)
        elif VaType.Sint16 == self.vaType:
            return "{}h".format(self.compCount)
        elif VaType.Sint8 == self.vaType:
            return "{}b".format(self.compCount)
        raise RuntimeError("Unsupported component vaType={}".format(self.vaType))


    def getSize(self):
        return self.getComponentSizeInBytes() * self.getComponentCount()


    def getComponentCount(self):
        return self.compCount


    def getComponentSizeInBytes(self):
        sz = 0
        if VaType.Float == self.vaType:
            sz = 4
        elif VaType.Uint32 == self.vaType:
            sz = 4
        elif VaType.Uint16 == self.vaType:
            sz = 2
        elif VaType.Uint8 == self.vaType:
            sz = 1
        elif VaType.Sint32 == self.vaType:
            sz = 4
        elif VaType.Sint16 == self.vaType:
            sz = 2
        elif VaType.Sint8 == self.vaType:
            sz = 1
        elif VaType.Float64 == self.vaType:
            sz = 8
        elif VaType.Uint64 == self.vaType:
            sz = 8
        elif VaType.Sint64 == self.vaType:
            sz = 8
        else:
            raise RuntimeError("Unsupported component vaType={}".format(self.vaType))
        return sz


# Vertex attributes container
# VATR  [cnt(U32)] vatr0, vatr1...
class VertexAttributes(object):
    def __init__(self, nr, chunk):
        self.__attribs = []

        semNameIdx = {}  # Semantic -> TotalIndex

        nr.seek(chunk.headerOffs)
        attribCount = nr.readU32()

        for idx in range(0, attribCount):
            vatr = VertexAttribute(nr)

            curIdx = semNameIdx.get(vatr.semantic, None)
            if None == curIdx:
                semNameIdx[vatr.semantic] = 0
                vatr.semIdx = 0
            else:
                curIdx += 1
                semNameIdx[vatr.semantic] = curIdx
                vatr.semIdx = curIdx

            self.__attribs.append(vatr)

    def getAttribsCount(self):
        return len(self.__attribs)

    def getAttr(self, idx):
        if idx >= self.getAttribsCount():
            return None
        return self.__attribs[idx]

    def findSemantic(self, name):
        res = []
        for idx in range(0, len(self.__attribs)):
            va = self.__attribs[idx]
            if va.semantic == name:
                res.append(va)
        return res


class Vertexes(object):
    def __VERT_headerSize(self):
      return 8

    def __init__(self, nr, chunk):
        self.__nr = nr
        self.__chunk = chunk
        nr.seek(chunk.headerOffs)
        self.__vertexCount = nr.readU32()
        self.__vertexSize  = nr.readU32()

    def getVertexCount(self):
        return self.__vertexCount

    def getVertexSize(self):
        return self.__vertexSize


    # Read all vertex data to buffer
    def read(self):
        self.__nr.seek(self.__chunk.headerOffs + self.__VERT_headerSize())
        return self.__nr.readBytes(self.__vertexCount * self.__vertexSize)


########################################################################
class Texture(object):
    def __init__(self, nr):
        self.reserved0 = nr.readU32()
        self.reserved1 = nr.readU32()
        self.fileName  = nr.readString()


class Textures(object):
    def __init__(self, nr, chunk):
        self.__textures = []

        nr.seek(chunk.headerOffs)
        texCount = nr.readU32()

        for idx in range(0, texCount):
            vatr = Texture(nr)
            self.__textures.append(vatr)

    def getTexturesCount(self):
        return len(self.__textures)

    def getTexture(self, idx):
        if idx < self.getTexturesCount():
            return self.__textures[idx]
        return None




########################################################################
class Shader(object):
    def __init__(self, nr):
        self.hashVal  = nr.readString()


class Shaders(object):
    def __init__(self, nr, chunk):
        self.__shaders = []

        nr.seek(chunk.headerOffs)
        shadersCount = nr.readU32()

        for idx in range(0, shadersCount):
            shader = Shader(nr)
            self.__shaders.append(shader)

    def getShadersCount(self):
        return len(self.__shaders)

    def getShader(self, idx):
        if idx < self.getShadersCount():
            return self.__shaders[idx]
        return None



########################################################################
# Single name-val
# TypeId
########################################################################

class NameVal(object):
    def __init__(self, nr):
        self.name   = nr.readString()
        self.type   = nr.readU16()
        self.length = nr.readU16()
        self.data   = nr.readBytes(self.length)

    def getValue(self):
        if TlvTypeId.Dword == self.type:
            dwVal = struct.unpack('I', self.data)[0]
            return dwVal
        if TlvTypeId.String == self.type:
            strVal = self.data.decode('utf-8') 
            return strVal

        return  None

# Name-Values container. Type-Len-Value (TLV)
# PROP  [TAG] [cnt(U32)] nameVal0(tlv), nameVal1(tlv)...
class Properties(object):
    def __init__(self, nr, chunk):
        self.__nameVals = []  # TODO: Dict

        nr.seek(chunk.headerOffs)
        self.tag      = nr.readU32()
        self.propsCnt = nr.readU32()

        for idx in range(0, self.propsCnt):
            nv = NameVal(nr)
            self.__nameVals.append(nv)

    def findByName(self, name):
        res = []
        for idx in range(0, len(self.__nameVals)):
            va = self.__nameVals[idx]
            if va.name == name:
                res.append(va)
        return res

    def getPropsCount(self):
        return len(self.__nameVals)

    def getProp(self, idx):
        if idx >= self.getPropsCount():
            return None
        return self.__nameVals[idx]

    def isTrue(self, name):
        val = self.getVal(name)
        if val:
            if int(val) != 0:
                return True
        return False

    def isFalse(self, name):
        return not self.isTrue(name)

    def getVal(self, name):
        res = None
        for idx in range(0, len(self.__nameVals)):
            val = self.__nameVals[idx]
            if val.name == name:
                res = val.getValue();
                break
        return res

    def getValue(self, name, defVal):
        res = defVal
        for idx in range(0, len(self.__nameVals)):
            val = self.__nameVals[idx]
            if val.name == name:
                res = val.getValue();
                break
        return res


##############################################################################

def ShaderStageToString(x):
    if ShaderStage.PreVs == x:
        return "PreVs"
    if ShaderStage.Vs == x:
        return "Vs"
    if ShaderStage.DsGs == x:
        return "DsGs"
    return "Unknown"


def topologyToStr(topo):
    if PrimitiveTopology.TriangleList == topo:
        return "TriangleList"
    elif PrimitiveTopology.LineList == topo:
        return "LineList"
    elif PrimitiveTopology.PointList == topo:
        return "PointList"
    return "Unknown"


def attrCompTypeToStr(t):
    if VaType.Float == t:
        return "Float"
    if VaType.Uint32 == t:
        return "Uint32"
    if VaType.Uint16 == t:
        return "Uint16"
    if VaType.Uint8 == t:
        return "Uint8"
    if VaType.Sint32 == t:
        return "Sint32"
    if VaType.Sint16 == t:
        return "Sint16"
    if VaType.Sint8 == t:
        return "Sint8"
    if VaType.Float64 == t:
        return "Float64"
    if VaType.Uint64 == t:
        return "Uint64"
    if VaType.Sint64 == t:
        return "Sint64"
    return "Unknown"
