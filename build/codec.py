"""Build-time LZ/Huffman archive and a native-only Python 3.4 source decoder.

Each stream resets its LZ history to a shared dictionary (at most 4096 bytes).
Streams expand to at most 5120 bytes; a source may join streams up to 16384 bytes.
The decoder reads base85 directly or uses packed byte records, without a second
compressed buffer. Output/history use bytearrays; no imports or file access.
"""
import ast
from collections import Counter
import heapq


CHUNK = 5120
MAX_SOURCE = 16384
DICT_SIZE = 4096
ALPHABET = ''.join(chr(i) for i in range(33, 127) if chr(i) not in "'\"\\")[:85]
LENGTHS = (3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 15, 17, 19, 23, 27,
           31, 35, 43, 51, 59, 67, 83, 99, 115, 131, 163, 195, 227, 258)


def _checksum(data):
    first, second = 1, 0
    for byte in data:
        first = (first + byte) % 65521
        second = (second + first) % 65521
    return (second << 16) | first


def _base85(value, bits):
    result = []
    for shift in range(((bits + 31) // 32 - 1) * 32, -1, -32):
        word = (value >> shift) & 0xffffffff
        chars = []
        for unused in range(5):
            word, digit = divmod(word, 85)
            chars.append(ALPHABET[digit])
        result.extend(reversed(chars))
    return ''.join(result)


def _dictionary(blocks, size):
    """Choose frequent substrings, deterministically, with suffix/prefix overlap."""
    if not size:
        return b''
    counts = Counter()
    for data in blocks:
        counts.update(line + b'\n' for line in data.splitlines() if 5 <= len(line) < 100)
        for width in (8, 16, 32, 64):
            counts.update(data[i:i + width] for i in range(0, len(data) - width + 1, 4))
    ranked = sorted((-(count - 1) * (len(word) - 3), word)
                    for word, count in counts.items() if count > 1)
    result = b''
    for score, word in ranked:
        if word in result:
            continue
        overlap = min(len(word) - 1, len(result))
        while overlap and result[-overlap:] != word[:overlap]:
            overlap -= 1
        tail = word[overlap:]
        if len(result) + len(tail) <= size:
            result += tail
        if len(result) >= size - 4:
            break
    return result


def _tokens(data, dictionary):
    """Lazy LZ77 with 258-byte matches and bounded build-time hash chains."""
    text = dictionary + data
    start = len(dictionary)
    end = len(text)
    chains = {}

    def add(pos):
        if pos + 3 <= end:
            key = text[pos:pos + 3]
            chain = chains.setdefault(key, [])
            chain.append(pos)
            if len(chain) > 128:
                del chain[:64]

    def match(pos):
        length, distance = 2, 0
        maximum = min(258, end - pos)
        if maximum < 3:
            return length, distance
        for other in reversed(chains.get(text[pos:pos + 3], ())):
            if other >= pos or pos - other > 32768:
                continue
            if length < maximum and text[other + length] != text[pos + length]:
                continue
            n = 3
            while n < maximum and text[other + n] == text[pos + n]:
                n += 1
            if n > length:
                length, distance = n, pos - other
                if n == maximum:
                    break
        return length, distance

    for pos in range(start):
        add(pos)
    pos = start
    result = []
    while pos < end:
        length, distance = match(pos)
        add(pos)
        if length < 3 or pos + 1 < end and match(pos + 1)[0] > length + 1:
            result.append(text[pos])
            pos += 1
            continue
        code = 28
        while LENGTHS[code] > length:
            code -= 1
        extra = 0 if code < 8 or code == 28 else (code - 4) // 4
        dbits = max(0, (distance - 1).bit_length() - 2)
        dcode = distance - 1 if distance <= 4 else 2 * dbits + ((distance - 1) >> dbits)
        dbase = dcode + 1 if dcode < 4 else ((2 + (dcode & 1)) << dbits) + 1
        result.append((257 + code, length - LENGTHS[code], extra,
                       dcode, distance - dbase, dbits))
        for nxt in range(pos + 1, pos + length):
            add(nxt)
        pos += length
    result.append(256)
    return result


def _huffman(frequency):
    """Canonical codes; deterministic ties and a one-bit singleton alphabet."""
    heap = [(count, symbol, (symbol,)) for symbol, count in sorted(frequency.items())]
    heapq.heapify(heap)
    lengths = {symbol: 0 for symbol in frequency}
    while len(heap) > 1:
        ac, ak, av = heapq.heappop(heap)
        bc, bk, bv = heapq.heappop(heap)
        values = av + bv
        for symbol in values:
            lengths[symbol] += 1
        heapq.heappush(heap, (ac + bc, min(ak, bk), values))
    order = sorted((max(1, length), symbol) for symbol, length in lengths.items())
    counts = bytearray(2 * (max(length for length, symbol in order) + 1))
    symbols = bytearray()
    codes = {}
    code = previous = 0
    for length, symbol in order:
        code <<= length - previous
        codes[symbol] = (code, length)
        count = counts[2 * length] * 256 + counts[2 * length + 1] + 1
        counts[2 * length:2 * length + 2] = bytes((count >> 8, count & 255))
        symbols.extend((symbol >> 8, symbol & 255))
        code += 1
        previous = length
    return codes, bytes(counts), bytes(symbols)


def _stream(data, tokens, literals, distances, storage):
    bits = value = 0
    for token in tokens:
        fields = (literals[token],) if isinstance(token, int) else (
            literals[token[0]], (token[1], token[2]),
            distances[token[3]], (token[4], token[5]))
        for field, width in fields:
            value = (value << width) | field
            bits += width
    if storage == 'bytes':
        payload = (value << ((-bits) % 8)).to_bytes((bits + 7) // 8, 'big')
    else:
        payload = _base85(value << ((-bits) % 32), bits)
    return (len(data), _checksum(data), bits, payload)


# No imports, recursion, eval, compressed-byte buffer, or large integer bitstream.
# Huffman counts/symbols are bytes, not hundreds of Python integer objects.
DECODER = '''_A={alphabet!r}
_LC={lc!r}
_LS={ls!r}
_DC={dc!r}
_DS={ds!r}
def _bits(s,n):
 if s[4]+n>s[5]:
  raise ValueError('corrupt source')
 v=0
 s[4]+=n
 while n:
  if not s[3]:
   w=0
   for j in range(5):
    c=_A.find(s[0][s[1]])
    s[1]+=1
    if c<0:
     raise ValueError('corrupt source')
    w=w*85+c
   if w>4294967295:
    raise ValueError('corrupt source')
   s[2]=w
   s[3]=32
  k=min(n,s[3])
  s[3]-=k
  v=(v<<k)|((s[2]>>s[3])&((1<<k)-1))
  n-=k
 return v
def _symbol(s,counts,symbols):
 code=first=index=0
 for n in range(1,len(counts)//2):
  if s[4]>=s[5]:
   raise ValueError('corrupt source')
  if not s[3]:
   w=0
   for j in range(5):
    c=_A.find(s[0][s[1]])
    s[1]+=1
    if c<0:
     raise ValueError('corrupt source')
    w=w*85+c
   if w>4294967295:
    raise ValueError('corrupt source')
   s[2]=w
   s[3]=32
  s[3]-=1
  s[4]+=1
  code=(code<<1)|((s[2]>>s[3])&1)
  count=counts[2*n]*256+counts[2*n+1]
  if 0<=code-first<count:
   i=2*(index+code-first)
   return symbols[i]*256+symbols[i+1]
  index+=count
  first=(first+count)<<1
 raise ValueError('corrupt source')
def _chunk(record,dictionary):
 if type(record) is not tuple or len(record)!=4:
  raise ValueError('corrupt source')
 size,checksum,nbits,text=record
 if type(size) is not int or size<0 or size>5120 or type(checksum) is not int or checksum<0 or checksum>4294967295 or type(nbits) is not int or nbits<1 or nbits>131072 or type(text) is not str or len(text)!=((nbits+31)//32)*5:
  raise ValueError('corrupt source')
 s=[text,0,0,0,0,nbits]
 out=bytearray()
 first,second=1,0
 while True:
  c=_symbol(s,_LC,_LS)
  if c==256:
   break
  if c<256:
   if len(out)>=size:
    raise ValueError('corrupt source')
   out.append(c)
   first=(first+c)%65521
   second=(second+first)%65521
  else:
   if c<=264:
    length=c-254
   elif c==285:
    length=258
   else:
    extra=(c-261)//4
    length=(((c-265)%4+4)<<extra)+3+_bits(s,extra)
   d=_symbol(s,_DC,_DS)
   if d<4:
    distance=d+1
   else:
    extra=d//2-1
    distance=((2+(d&1))<<extra)+1+_bits(s,extra)
   if distance>len(dictionary)+len(out) or len(out)+length>size:
    raise ValueError('corrupt source')
   for j in range(length):
    p=len(out)-distance
    c=dictionary[len(dictionary)+p] if p<0 else out[p]
    out.append(c)
    first=(first+c)%65521
    second=(second+first)%65521
 if len(out)!=size or (second<<16)|first!=checksum or s[4]!=nbits or s[2]&((1<<s[3])-1):
  raise ValueError('corrupt source')
 return out
_DICT=_chunk({dictionary!r},b'')
def _decode_bytes(records):
 if type(records) is not tuple or not records or len(records)>4:
  raise ValueError('corrupt source')
 out=bytearray()
 for record in records:
  block=_chunk(record,_DICT)
  if len(out)+len(block)>16384:
   raise ValueError('corrupt source')
  out.extend(block)
 return out
def _decode(records):
 if type(records) is not tuple or not records or len(records)>4:
  raise ValueError('corrupt source')
 parts=[]
 size=0
 for record in records:
  block=_chunk(record,_DICT)
  size+=len(block)
  if size>16384:
   raise ValueError('corrupt source')
  parts.append(block.decode('ascii'))
  del block
 return ''.join(parts)
'''


BYTE_DECODE = '''def _decode(records,binary=False):
 if type(records) is not bytes or not records or not 0<records[0]<=4:
  raise ValueError('corrupt source')
 parts=[]
 out=bytearray() if binary else None
 pos=1
 size=0
 for j in range(records[0]):
  if pos+9>len(records):
   raise ValueError('corrupt source')
  n=records[pos]*256+records[pos+1]
  checksum=(records[pos+2]<<24)|(records[pos+3]<<16)|(records[pos+4]<<8)|records[pos+5]
  nbits=(records[pos+6]<<16)|(records[pos+7]<<8)|records[pos+8]
  start=pos+9
  pos=start+(nbits+7)//8
  if pos>len(records) or size+n>16384:
   raise ValueError('corrupt source')
  block=_chunk((n,checksum,nbits,records,start,pos),_DICT)
  size+=n
  if binary:
   out.extend(block)
  else:
   parts.append(block.decode('ascii'))
  del block
 if pos!=len(records):
  raise ValueError('corrupt source')
 return out if binary else ''.join(parts)
def _decode_bytes(records):
 return _decode(records,True)
'''


def _binary_decoder(source):
    """Specialize the bit reader; flat headers cost no persistent tuple/int objects."""
    source = source[:source.index('def _decode_bytes(records):')] + BYTE_DECODE
    reader = '''   w=0
   for j in range(5):
    c=_A.find(s[0][s[1]])
    s[1]+=1
    if c<0:
     raise ValueError('corrupt source')
    w=w*85+c
   if w>4294967295:
    raise ValueError('corrupt source')
   s[2]=w
   s[3]=32'''
    source = source.replace(reader, '''   s[2]=s[0][s[1]]
   s[1]+=1
   s[3]=8''')
    source = source.replace("_A=" + repr(ALPHABET) + '\n', '')
    source = source.replace('len(record)!=4', 'len(record)!=6')
    source = source.replace('size,checksum,nbits,text=record', 'size,checksum,nbits,text,start,end=record')
    source = source.replace("type(text) is not str or len(text)!=((nbits+31)//32)*5",
                            "type(text) is not bytes or start<0 or end>len(text) or end-start!=(nbits+7)//8")
    return source.replace('s=[text,0,0,0,0,nbits]', 's=[text,start,0,0,0,nbits]')


def _encode(sources, dictionary_size, storage):
    pieces = {name: [data[i:i + CHUNK] for i in range(0, len(data), CHUNK)] or [b'']
              for name, data in sources.items()}
    dictionary = _dictionary([p for ps in pieces.values() for p in ps], dictionary_size)
    dtokens = _tokens(dictionary, b'')
    tokenized = {name: [_tokens(p, dictionary) for p in ps] for name, ps in pieces.items()}
    all_tokens = [dtokens] + [t for ts in tokenized.values() for t in ts]
    lf, df = Counter(), Counter({0: 1})
    for tokens in all_tokens:
        for token in tokens:
            if isinstance(token, int):
                lf[token] += 1
            else:
                lf[token[0]] += 1
                df[token[3]] += 1
    lcodes, lc, ls = _huffman(lf)
    dcodes, dc, ds = _huffman(df)
    dstream = _stream(dictionary, dtokens, lcodes, dcodes, storage)
    archive = {name: tuple(_stream(p, t, lcodes, dcodes, storage) for p, t in zip(ps, tokenized[name]))
               for name, ps in pieces.items()}
    if storage == 'bytes':
        dstream += (0, len(dstream[3]))
    decoder = DECODER.format(alphabet=ALPHABET, lc=lc, ls=ls, dc=dc, ds=ds, dictionary=dstream)
    if storage == 'bytes':
        flat = {}
        for name, records in archive.items():
            payload = bytearray((len(records),))
            for size, checksum, bits, text in records:
                payload.extend(size.to_bytes(2, 'big'))
                payload.extend(checksum.to_bytes(4, 'big'))
                payload.extend(bits.to_bytes(3, 'big'))
                payload.extend(text)
            flat[name] = bytes(payload)
        archive = flat
        decoder = _binary_decoder(decoder)
    return archive, decoder


def encode_blocks(sources, dictionary_size=DICT_SIZE, storage='base85'):
    """Return ``(archive, decoder_source)``; decoder defines ``_decode(record)``.

    Keys are names and values are ASCII source strings or arbitrary bytes.
    ``_decode_bytes`` supports binary round trips; ``_decode`` returns ASCII str.
    Each block is checksummed and independent of load order. The shared dictionary
    is selected only when its complete decoder/archive representation saves space.
    storage='bytes' uses ASCII-escaped bytes literals, reducing resident payload
    by about 20% at the cost of a larger source file. Its headers are packed into
    each byte string rather than persistent tuples and Python integer objects.
    """
    if not isinstance(dictionary_size, int) or not 0 <= dictionary_size <= DICT_SIZE:
        raise ValueError('dictionary size must be between 0 and 4096')
    if storage not in ('base85', 'bytes'):
        raise ValueError('storage must be base85 or bytes')
    normalized = {}
    for name in sorted(sources):
        value = sources[name]
        if not isinstance(name, str) or not isinstance(value, (str, bytes)):
            raise ValueError('expected named source strings or bytes')
        data = value.encode('ascii') if isinstance(value, str) else value
        if len(data) > MAX_SOURCE:
            raise ValueError('source exceeds 16384 bytes: ' + name)
        normalized[name] = data
    plain = _encode(normalized, 0, storage)
    if not dictionary_size:
        return plain
    shared = _encode(normalized, dictionary_size, storage)
    if storage == 'bytes':
        # Include the persistent decoded dictionary and Huffman bytes, not repr escapes.
        def memory(result):
            ns = {}
            exec(result[1], ns)
            constants = sum(len(node.value) for node in ast.walk(ast.parse(result[1]))
                            if isinstance(node, ast.Constant) and isinstance(node.value, bytes))
            return sum(map(len, result[0].values())) + len(ns['_DICT']) + constants
        return min((plain, shared), key=memory)
    return min((plain, shared), key=lambda result: len(repr(result[0])) + len(result[1]))
