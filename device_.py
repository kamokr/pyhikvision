import contextlib
import ctypes
import datetime
import glob
import logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s [%(levelname)s] %(message)s')
import os
import queue
import threading
import time
import uuid
from collections import OrderedDict

import av

from .errors import *
from .sdk import *


MAX_PLAY_CTX = 4
MAX_SEEK_TRIES = 3
SEGMENT_LENGTH = 2
INITIAL_SEGMENT_LENGTH = 1


def local2ts(dt):
    return int(datetime.datetime.timestamp(dt)*1000)

def ts2local(ts):
    return datetime.datetime.fromtimestamp(ts/1000)


class HikvisionSDKError(Exception):
    def __init__(self, error_code):
        self.error_code = error_code
        super().__init__('error code {}'.format(error_code))


class SearchResult:
    filename = None
    size = None
    start = None
    stop = None

    def __repr__(self):
        return '{}(filename="{}", size={}, start={}, stop={})'.format(
            self.__class__.__name__,
            self.filename,
            self.size,
            self.start,
            self.stop)


def _login_result_cb(lUserID, dwResult, lpDeviceInfo, pUser):
    logging.debug('fLoginResultCallBack()')
_c_login_result_cb = fLoginResultCallBack(_login_result_cb)


class PlayContext:
    def __init__(self, play_id, play_handle, channel, seek_ts):
        self.play_id = play_id
        self.play_handle = play_handle
        self.channel = channel
        self.seek_ts = seek_ts

        self.frame_n = 0
        self.duration = 0
        self.segment_start_ts = None
        self.segment_0_start_ts = None
        self.sequence = 0
        self.segment = 0
        self.hold_cb = threading.Lock()
        self.file_is_ready = threading.Lock()
        self.file_is_ready.acquire()
        self.playback_started = False

        self.filename = None
        self.file = None
        self.stream = None
        self.prev_output_frame_ts = 0

    def as_dict(self):
        return {
            'play_handle': self.play_handle,
            'play_id': self.play_id,
            'playback_started': self.playback_started,
            'channel': self.channel,
            'segment': self.segment,
            'seek_ts': self.seek_ts,
            'segment_start_ts': self.segment_start_ts,
            'segment_0_start_ts': self.segment_0_start_ts,
            'filename': self.filename,
        }


@contextlib.contextmanager
def initialized():
    try:
        _init()
        yield
    except:
        raise
    finally:
        _cleanup() 


def _init(connect_time=10000, recv_timeout=10000):
    logging.debug('NET_DVR_Init()')
    result = NET_DVR_Init()
    if not result:
        error_code = NET_DVR_GetLastError()
        raise HikvisionSDKError(error_code)

    logging.debug('NET_DVR_SetConnectTime({})'.format(connect_time))
    NET_DVR_SetConnectTime(connect_time, 3)

    logging.debug('NET_DVR_SetRecvTimeOut({})'.format(recv_timeout))
    NET_DVR_SetRecvTimeOut(recv_timeout)
    
    
def _cleanup():
    logging.debug('NET_DVR_Cleanup()')
    result = NET_DVR_Cleanup()
    if not result:
        error_code = NET_DVR_GetLastError()
        raise HikvisionSDKError(error_code)


class Device(threading.Thread):
    def __init__(self, name, host, port, username, password):
        threading.Thread.__init__(self)

        self._name = name
        self._host = host
        self._port = port
        self._username = username
        self._password = password

        self._terminate = False
        self._want_connect = False
        self._int_status = 'disconnected'
        self._error_code = 0

        self._queue = queue.Queue()
        self._results = {} # lock: result

        self._buffer_queue = queue.Queue()

        self._user_id = None
        self._play_ctx = OrderedDict() # play_id: play_handle
        self._play_handle = None

        self._login_info = NET_DVR_USER_LOGIN_INFO()
        self._c_device_info = NET_DVR_DEVICEINFO_V40()

        # device info
        self._serial_number = ''
        self._start_channel = 0
        self._num_channels = 0
        self._start_dchannel = 0
        self._num_dchannels = 0

        self._play_data_cb = None
        def _play_data_cb(lPlayHandle, dwDataType, pBuffer, dwBufSize, pUser):
            # logging.debug('fPlayDataCallBack_V40()')
            if callable(self._play_data_cb):
                self._play_data_cb(lPlayHandle, dwDataType, pBuffer, dwBufSize, pUser)

        self._c_play_data_cb = fPlayDataCallBack_V40(_play_data_cb)
        self._c_play_es_cb = fPlayESCallBack(self._play_es_cb)

    def __repr__(self):
        return '{}("{}", "{}", {}, "{}")'.format(
            self.__class__.__name__,
            self._name,
            self._host,
            self._port,
            self._username
        )

    @property
    def _status(self):
        return self._int_status
    
    @_status.setter
    def _status(self, new):
        if self._int_status != new:
            logging.debug('{} status changed {} -> {}'.format(
                self,
                self._int_status,
                new
            ))
            self._int_status = new

    @contextlib.contextmanager
    def _connect(self):
        self._login()
        try:
            yield
        except:
            raise
        finally:
            self._stop_all_playback()
            self._logout()

    def _login(self):
        logging.debug('NET_DVR_Login_V40()')
        self._login_info.sDeviceAddress = self._host.encode('ascii')
        self._login_info.byUseTransport = 0
        self._login_info.wPort = self._port
        self._login_info.sUserName = self._username.encode('ascii')
        self._login_info.sPassword = self._password.encode('ascii')
        self._login_info.cbLoginResult = _c_login_result_cb
        self._login_info.pUser = None
        self._login_info.bUseAsynLogin = 0
        self._login_info.byProxyType = 0
        self._login_info.byUseUTCTime = 0
        self._login_info.byLoginMode = 0
        self._login_info.byHttps = 0
        self._login_info.iProxyID = 0
        self._login_info.byVerifyMode = 0
        self._login_info.byRes3 = (BYTE * 119)(*([0] * 119))

        result = NET_DVR_Login_V40(ctypes.byref(self._login_info), ctypes.byref(self._c_device_info))
        if result == -1:
            error_code = NET_DVR_GetLastError()
            raise HikvisionSDKError(error_code)
        
        self._user_id = result

        self._serial_number = ctypes.cast(self._c_device_info.struDeviceV30.sSerialNumber, ctypes.c_char_p).value.decode('ascii')
        self._start_channel = self._c_device_info.struDeviceV30.byStartChan
        self._num_channels = self._c_device_info.struDeviceV30.byChanNum
        self._start_dchannel = self._c_device_info.struDeviceV30.byStartDChan
        self._num_dchannels = self._c_device_info.struDeviceV30.byIPChanNum

        logging.debug('    user ID: {}'.format(self._user_id))
        logging.debug('    serial number: {}'.format(self._serial_number))
        logging.debug('    start channel: {}'.format(self._start_channel))
        logging.debug('    num channels: {}'.format(self._num_channels))
        logging.debug('    start digital channel: {}'.format(self._start_dchannel))        
        logging.debug('    num digital channels: {}'.format(self._num_dchannels))

    def _logout(self):
        logging.debug('NET_DVR_Logout()')
        result = NET_DVR_Logout(self._user_id)

        if not result:
            error_code = NET_DVR_GetLastError()
            raise HikvisionSDKError(error_code)
        
    def _search(self, channel, file_type, start_time: datetime.datetime, stop_time: datetime.datetime):
        channel = channel
        file_type = file_type

        _start_time = NET_DVR_TIME.from_datetime(start_time)
        _stop_time = NET_DVR_TIME.from_datetime(stop_time)
        
        logging.debug('NET_DVR_FindFile()')
        result = NET_DVR_FindFile(self._user_id, channel, file_type, ctypes.byref(_start_time), ctypes.byref(_stop_time))
        if result == -1:
            error_code = NET_DVR_GetLastError()
            raise HikvisionSDKError(error_code)
        
        find_handle = result

        NET_DVR_FILE_SUCCESS = 1000 # Get the file information successfully
        NET_DVR_FILE_NOFIND = 1001 # No file found
        NET_DVR_ISFINDING = 1002 # Searching, please wait
        NET_DVR_NOMOREFILE = 1003 # No more file found, search is finished 
        NET_DVR_FILE_EXCEPTION = 1004 # Exception when search file

        search_results = []
        find_data = sdk.NET_DVR_FIND_DATA()

        while True:
            try:
                logging.debug('NET_DVR_FindNextFile()')
                result = NET_DVR_FindNextFile(find_handle, ctypes.byref(find_data))
                if result == -1:
                    error_code = NET_DVR_GetLastError()
                    raise HikvisionSDKError(error_code)

            except Exception as ex:
                logging.exception(ex)
                break
            else:
                if result == NET_DVR_FILE_SUCCESS:  
                    r = SearchResult()
                    r.filename = ctypes.cast(find_data.sFileName, ctypes.c_char_p).value.decode('ascii')
                    r.size = find_data.dwFileSize
                    r.start = find_data.struStartTime.as_datetime()
                    r.stop = find_data.struStopTime.as_datetime()
                    search_results.append(r)

                if result == NET_DVR_FILE_NOFIND:
                    logging.debug('NET_DVR_FindNextFile(): no files found')
                    break   
                if result == NET_DVR_NOMOREFILE:
                    logging.debug('NET_DVR_FindNextFile(): no more files')
                    break 
                if result == NET_DVR_FILE_EXCEPTION:
                    logging.debug('NET_DVR_FindNextFile(): exception during searching')
                    break 
                if result == NET_DVR_ISFINDING:
                    logging.debug('NET_DVR_FindNextFile(): searching...')
                    time.sleep(0.1)

        logging.debug('NET_DVR_FindClose()')
        result = sdk.NET_DVR_FindClose(find_handle)
        if not result:
            error_code = sdk.NET_DVR_GetLastError()
            raise HikvisionSDKError(error_code)
        
        return search_results

    def _playback_control(self, control_code):
        logging.debug('NET_DVR_PlayBackControl({})'.format(control_code))

        result = sdk.NET_DVR_PlayBackControl(self._play_handle, control_code, 0, None)
        if not result:
            error_code = sdk.NET_DVR_GetLastError()
            raise HikvisionSDKError(error_code)
        
    def _playback_control_v40(self, control_code):
        logging.debug('NET_DVR_PlayBackControl_V40({})'.format(control_code))

        result = sdk.NET_DVR_PlayBackControl_V40(self._play_handle, control_code, None, 0, None, 0)
        if not result:
            error_code = sdk.NET_DVR_GetLastError()
            raise HikvisionSDKError(error_code)
        
    def _play_start(self):
        logging.debug('NET_DVR_PlayBackControl_V40()')

        a = (sdk.BYTE * 4)(2) # 1- PS, 2- TS, 3- RTP, 5- MP4
        result = sdk.NET_DVR_PlayBackControl_V40(self._play_handle, sdk.PlayBackControl.NET_DVR_SET_TRANS_TYPE, ctypes.byref(a), 4, None, 0)
        if not result:
            error_code = sdk.NET_DVR_GetLastError()
            raise HikvisionSDKError(error_code)

        result = sdk.NET_DVR_PlayBackControl_V40(self._play_handle, sdk.PlayBackControl.NET_DVR_PLAYSTART, None, 0, None, 0)
        if not result:
            error_code = sdk.NET_DVR_GetLastError()
            raise HikvisionSDKError(error_code)
        
    def _play_get_pos(self):
        pos = sdk.DWORD()

        result = sdk.NET_DVR_PlayBackControl_V40(
            self._play_handle, 
            sdk.PlayBackControl.NET_DVR_PLAYGETPOS, 
            None, 
            0, 
            ctypes.byref(pos), 
            ctypes.sizeof(pos))
        if not result:
            error_code = sdk.NET_DVR_GetLastError()
            raise HikvisionSDKError(error_code)
        
        return pos

    def _set_play_es_cb(self, play_es_cb):
        logging.debug('NET_DVR_SetPlayBackESCallBack()')

        self._play_es_cb = play_es_cb

        if self._play_handle is None:
            logging.warning('lPlayHandle is None, first call NET_DVR_PlayBackBy*')

        result = NET_DVR_SetPlayBackESCallBack(
            self._play_handle,
            self._c_play_es_cb,
            None)

        if not result:
            error_code = NET_DVR_GetLastError()
            raise HikvisionSDKError(error_code)
        
    def _stop_all_playback(self):
        for play_ctx in self._play_ctx.values():
            try:
                play_ctx.playback_started = False
                try:
                    play_ctx.hold_cb.release()
                except:
                    pass

                self._clear_tmp(play_ctx)


                logging.debug('NET_DVR_StopPlayBack({})'.format(play_ctx.play_handle))
                result = NET_DVR_StopPlayBack(play_ctx.play_handle)
                if not result:
                    error_code = NET_DVR_GetLastError()
                    raise HikvisionSDKError(error_code)
            except Exception as ex:
                logging.exception(ex)
        self._play_ctx = OrderedDict()
        
    def _seek(self, channel, ts):
        # stop playback of oldest file
        if len(self._play_ctx) >= MAX_PLAY_CTX:
            # get oldest play_ctx and stop it
            play_id, play_ctx = next(iter(self._play_ctx.items()))
            play_ctx.playback_started = False
            try:
                play_ctx.hold_cb.release()
            except:
                pass

            self._clear_tmp(play_ctx)

            logging.debug('NET_DVR_StopPlayBack({})'.format(play_ctx.play_handle))
            result = NET_DVR_StopPlayBack(play_ctx.play_handle)
            if not result:
                error_code = NET_DVR_GetLastError()
                raise HikvisionSDKError(error_code)
            
            self._play_ctx.pop(play_id, None)
            
        start_dt = ts2local(ts)
        stop_dt = ts2local((int(time.time())-15)*1000)
        
        # we have to loop since sometimes the SDK returns error code 102 (playback failed) and retrying helps
        tries = MAX_SEEK_TRIES
        while True:
            logging.debug('NET_DVR_PlayBackByTime()')
            play_handle = NET_DVR_PlayBackByTime(
                self._user_id,
                channel,
                NET_DVR_TIME.from_datetime(start_dt),
                NET_DVR_TIME.from_datetime(stop_dt),
                0)
            
            if play_handle == -1:
                tries -= 1
                if tries > 0:
                    continue

                error_code = NET_DVR_GetLastError()
                raise HikvisionSDKError(error_code)
            break
        logging.debug('NET_DVR_PlayBackByTime() play handle = {}'.format(play_handle))

        play_id = str(uuid.uuid4())
        play_ctx = PlayContext(
            play_id,
            play_handle,
            channel,
            ts
        )
        self._play_ctx[play_id] = play_ctx # store playhandle
        return play_ctx
    
    def _clear_tmp(self, play_ctx):
        files = glob.glob('tmp/{}.*.ts'.format(play_ctx.play_id))
        with contextlib.suppress(FileNotFoundError):
            for f in files:
                os.remove(f)

    
    def _play(self, play_id):
        logging.debug('{} _play("{}")'.format(self, play_id))
        # get play_ctx from play_id (uuid) or play_handle (int)
        try:
            play_handle = int(play_id)
            play_ctx = None
            for ctx in self._play_ctx.values():
                if ctx.play_handle == play_handle:
                    play_ctx = ctx
                    break
            if play_ctx is None:    
                logging.error('{} invalid play handle {}'.format(self, play_id))
                return
        except:
            try:
                play_ctx = self._play_ctx[play_id]
            except KeyError:
                logging.error('{} invalid play_id'.format(self))
                return
        
        if play_ctx.playback_started:
            play_ctx.hold_cb.release()
            play_ctx.file_is_ready.acquire()

            return play_ctx

        logging.debug('NET_DVR_SetPlayBackESCallBack()')
        result = NET_DVR_SetPlayBackESCallBack(
            play_ctx.play_handle,
            self._c_play_es_cb,
            None)

        if not result:
            error_code = NET_DVR_GetLastError()
            raise HikvisionSDKError(error_code)

        result = NET_DVR_PlayBackControl_V40(play_ctx.play_handle, PlayBackControl.NET_DVR_PLAYSTART, None, 0, None, 0)
        if not result:
            error_code = NET_DVR_GetLastError()
            raise HikvisionSDKError(error_code)
        
        play_ctx.playback_started = True
        play_ctx.hold_cb.acquire()
        play_ctx.file_is_ready.acquire()

        return play_ctx

    def _play_es_cb(self, lPlayHandle, struPackInfo, pUser):
        if struPackInfo.contents.dwPacketType not in [1, 3]:
            return

        frame_dt = datetime.datetime(
            year = struPackInfo.contents.dwYear,
            month = struPackInfo.contents.dwMonth,
            day = struPackInfo.contents.dwDay,
            hour = struPackInfo.contents.dwHour,
            minute = struPackInfo.contents.dwMinute,
            second = struPackInfo.contents.dwSecond,
            microsecond = struPackInfo.contents.dwMillisecond*1000,
        )
        frame_ts = local2ts(frame_dt)

        # find in which play_ctx we are based on lPlayHandle value
        play_ctx = None
        for ctx in self._play_ctx.values():
            if ctx.play_handle == lPlayHandle:
                play_ctx = ctx
                break

        if play_ctx is None:
            logging.debug('{} invalid play handle {}'.format(self, lPlayHandle))
            return
        
        logging.debug('{} play handle {} got frame type: {}, ts: {}, play_ctx.seek_ts: {}'.format(
            self,
            play_ctx.play_handle,
            struPackInfo.contents.dwPacketType,
            frame_ts,
            play_ctx.seek_ts
        ))
          
        # set initial timestamp values
        if play_ctx.segment_start_ts is None:
            play_ctx.segment_start_ts = frame_ts
        
        if play_ctx.segment_0_start_ts is None:
            play_ctx.segment_0_start_ts = frame_ts
        
        # we have over 10 s and next frame is key
        if play_ctx.segment == 0:
            wanted_segment_length = INITIAL_SEGMENT_LENGTH
        else:
            wanted_segment_length = SEGMENT_LENGTH

        # check if segment capturing is over
        # - for segment zero we capture only first frame which is an I frame (fast seeking)
        # - for consecutive segments we capture until we have enough segment length and an I frame i received
        # if (play_ctx.segment == 0 and play_ctx.frame_n == 1) or \
        #     (frame_ts > play_ctx.segment_start_ts + wanted_segment_length*1000-250 and struPackInfo.contents.dwPacketType == 1):
        if frame_ts > play_ctx.segment_start_ts + wanted_segment_length*1000-250 and struPackInfo.contents.dwPacketType == 1:
            play_ctx.file.close()
            play_ctx.file = None
            
            play_ctx.duration = frame_ts - play_ctx.segment_start_ts

            play_ctx.file_is_ready.release() # signal file is ready
            play_ctx.hold_cb.acquire() # hold callback, wait for next play command

            # we can remove the file since the next file was requested
            with contextlib.suppress(FileNotFoundError): os.remove(play_ctx.filename)

            # init new segment
            play_ctx.segment_start_ts = frame_ts # new segment 
            play_ctx.segment += 1
            play_ctx.frame_n = 0
            play_ctx.prev_output_frame_ts = 0
            play_ctx.sequence += 1

        # exit if done
        if play_ctx.playback_started == False:
            return
        
        if play_ctx.file is None:
            ts_filename = 'tmp/{}.{:016d}.{}.ts'.format(
                play_ctx.play_id,
                play_ctx.segment_0_start_ts,
                play_ctx.segment
            )
            play_ctx.filename = ts_filename
            play_ctx.file = av.open(ts_filename, 'w', format='mpegts')
            play_ctx.stream = play_ctx.file.add_stream('h264')
        
        # save current frame buffer
        if struPackInfo.contents.dwPacketType in [1, 3]:
            buf = ctypes.cast(
                struPackInfo.contents.pPacketBuffer,
                ctypes.POINTER(ctypes.c_ubyte * struPackInfo.contents.dwPacketSize))
            # play_ctx.file.write(bytes(buf.contents))
            self._write_buffer(play_ctx, frame_ts, bytes(buf.contents))

        play_ctx.frame_n += 1 

    def _write_buffer(self, play_ctx, frame_ts, buffer_data):
        output_frame_ts = (frame_ts - play_ctx.segment_0_start_ts)*90

        if play_ctx.prev_output_frame_ts >= output_frame_ts:
            output_frame_ts = play_ctx.prev_output_frame_ts + 1
        play_ctx.prev_output_frame_ts = output_frame_ts

        packet = av.Packet(len(buffer_data))
        packet.stream = play_ctx.stream
        packet.dts = output_frame_ts
        packet.pts = output_frame_ts
        packet.update(buffer_data)

        play_ctx.file.mux(packet)

    def _call_and_wait(self, cmd, param):
        lock = threading.Lock()
        lock.acquire()
        self._queue.put((
            cmd,
            param,
            lock
        ))
        lock.acquire()
        lock.release()
        result = self._results[lock]
        self._results.pop(lock, None)
        return result
    
    def _get_result(self, method, param, lock):
        try:
            result = method(*param)
            self._results[lock] = result
        except Exception as ex:
            logging.exception(ex)
            self._results[lock] = None
        finally:
            lock.release()
        
    def _disconnected_loop(self):
        while not self._terminate and not self._want_connect:
            try:
                cmd, param, lock = self._queue.get(block=True, timeout=0.5)   
            except queue.Empty:
                continue
            if cmd == 'connect':
                self._want_connect = True
                continue

            if lock is not None:
                self._results[lock] = []
                lock.release()

    def _connected_loop(self):
        while not self._terminate and self._want_connect:
            try:
                with self._connect():
                    self._status = 'connected'
                    while not self._terminate and self._want_connect:
                        try:
                            cmd, param, lock = self._queue.get(block=True, timeout=0.5)
                        except queue.Empty:
                            continue

                        if cmd == 'disconnect':
                            self._want_connect = False
                            continue

                        if cmd == 'search':
                            self._get_result(self._search, param, lock)
                            continue

                        if cmd == 'seek':
                            self._get_result(self._seek, param, lock)
                            continue

                        if cmd == 'play':
                            self._get_result(self._play, param, lock)
                            continue

                        logging.debug('{} {} is not implemented'.format(self, cmd))
                        if lock is not None:
                            self._results[lock] = []
                            lock.release()

                        # if cmd == 'mp4':
                        #     self._play(None)
                        #     continue

                self._status = 'disconnected'

            except HikvisionSDKError as e:
                logging.exception(e)
                self._status = 'error'
                time.sleep(1)

    @property
    def play_ctx(self):
        return self._play_ctx

    @property
    def name(self):
        return self._name
        
    @property
    def serial_number(self):
        return self._serial_number
        
    @property
    def status(self):
        return self._int_status

    def connect(self):
        self._queue.put(('connect', None, None))

    def disconnect(self):
        self._queue.put(('disconnect', None, None))

    def seek(self, channel, ts):
        return self._call_and_wait('seek', (channel, ts))
    
    def play(self, play_id):
        return self._call_and_wait('play', (play_id,))

    def search(self, channel, file_type, start_time: datetime.datetime, stop_time: datetime.datetime):
        return self._call_and_wait('search', (channel, file_type, start_time, stop_time))

    def run(self):
        logging.debug('{} thread started'.format(self))
        while not self._terminate:
            self._disconnected_loop()
            self._connected_loop()
        logging.debug('{} thread terminated'.format(self))
        for ctx in self._play_ctx.values():
            ctx.playback_started = False
            try:
                ctx.hold_cb.release()
            except:
                pass
            try:
                ctx.file_is_ready.release()
            except:
                pass

    def stop(self):
        self._terminate = True


