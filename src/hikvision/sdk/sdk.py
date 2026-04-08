"""Python low-level bindings for Hikvision SDK."""
import ctypes as c
import datetime
import logging
import os
import platform
import sys
from importlib import resources


SDK_ENV_PATH = "HIKVISION_SDK_PATH"


def _normalized_machine():
    machine = platform.machine().lower()
    aliases = {
        "amd64": "x86_64",
        "x64": "x86_64",
        "x86-64": "x86_64",
    }
    return aliases.get(machine, machine)

def _platform_vendor_info():
    machine = _normalized_machine()
    if sys.platform.startswith("linux"):
        if machine == "x86_64":
            return os.path.join("vendor", "linux-x86_64"), ("libhcnetsdk.so",)
        raise RuntimeError(f"Unsupported Linux architecture: {machine}")

    if sys.platform.startswith("win"):
        if machine == "x86_64":
            return os.path.join("vendor", "win-amd64"), ("HCNetSDK.dll", "hcnetsdk.dll")
        raise RuntimeError(f"Unsupported Windows architecture: {machine}")

    raise RuntimeError(f"Unsupported platform: {sys.platform} ({machine})")

def _resolve_sdk_dir():
    override_dir = os.getenv(SDK_ENV_PATH)
    if override_dir:
        override_dir = os.path.abspath(override_dir)
        if not os.path.isdir(override_dir):
            raise FileNotFoundError(f"{SDK_ENV_PATH} points to non-existent directory: {override_dir}")
        logging.debug("Using SDK directory from %s: %s", SDK_ENV_PATH, override_dir)
        return override_dir
    
    vendor_rel_dir, _ = _platform_vendor_info()
    pkg_root = resources.files("hikvision")
    sdk_dir = os.fspath(pkg_root.joinpath(vendor_rel_dir))

    if not os.path.isdir(sdk_dir):
        raise FileNotFoundError(
            f"Packaged SDK directory not found: {sdk_dir}. "
            "Verify package-data includes vendor binaries."
        )

    return sdk_dir

def _load_hcnetsdk():
    sdk_dir = _resolve_sdk_dir()
    _, candidate_libs = _platform_vendor_info()

    if sys.platform.startswith("win") and hasattr(os, "add_dll_directory"):
        os.add_dll_directory(sdk_dir)

    for lib_name in candidate_libs:
        fullpath = os.path.join(sdk_dir, lib_name)
        if os.path.isfile(fullpath):
            logging.debug("Loading Hikvision SDK: %s", fullpath)
            return c.CDLL(fullpath)

    raise FileNotFoundError(
        f"Could not find SDK binary in {sdk_dir}. Tried: {', '.join(candidate_libs)}"
    )

try:
    libhcnetsdk = _load_hcnetsdk()
except OSError:
    logging.critical("Loading external libraries failed", exc_info=True)
    raise
except Exception:
    logging.critical("SDK runtime resolution failed", exc_info=True)
    raise

# #define  BOOL  int
# typedef  unsigned int       DWORD;
# typedef  unsigned short     WORD;
# typedef  unsigned short     USHORT;
# typedef  short              SHORT;
# typedef  int                LONG;
# typedef  unsigned char      BYTE;
# typedef  unsigned int       UINT;
# typedef  void*              LPVOID;
# typedef  void*              HANDLE;
# typedef  unsigned int*      LPDWORD; 
# typedef  unsigned long long UINT64;
# typedef  signed long long   INT64;
BOOL = c.c_int
DWORD = c.c_uint
WORD = c.c_ushort
USHORT = c.c_ushort
SHORT = c.c_short
LONG = c.c_int
BYTE = c.c_ubyte
UINT = c.c_uint
LPVOID = c.c_void_p
HANDLE = c.c_void_p
LPDWORD = c.POINTER(DWORD)
UINT64 = c.c_ulonglong
INT64 = c.c_longlong

# typedef unsigned int HWND;
HWND = c.c_uint

# //Macro definition 
# #define MAX_NAMELEN                 16      //DVR's local Username
# #define MAX_RIGHT                   32      //Authority permitted by Device (1- 12 for local authority,  13- 32 for remote authority) 
# #define NAME_LEN                    32      //Username length
# #define MIN_PASSWD_LEN              8       //min password length
# #define PASSWD_LEN                  16      //Password length
# #define STREAM_PASSWD_LEN           12      //stream password length
# #define MAX_PASSWD_LEN_EX           64      //Password length 64 bit
# #define GUID_LEN                    16      //GUID length
# #define DEV_TYPE_NAME_LEN           24      //Device name length
# #define SERIALNO_LEN                48      //SN length
SERIALNO_LEN = 48


# NET_DVR_API BOOL __stdcall NET_DVR_Init();
NET_DVR_Init = libhcnetsdk.NET_DVR_Init
NET_DVR_Init.argtypes = None
NET_DVR_Init.restype = BOOL

# NET_DVR_API BOOL __stdcall NET_DVR_Cleanup();
NET_DVR_Cleanup = libhcnetsdk.NET_DVR_Cleanup
NET_DVR_Cleanup.argtypes = None
NET_DVR_Cleanup.restype = BOOL

# typedef struct
# {
#     BYTE sSerialNumber[SERIALNO_LEN];    //SN
#     BYTE byAlarmInPortNum;                 //Number of Alarm input
#     BYTE byAlarmOutPortNum;                 //Number of Alarm Output
#     BYTE byDiskNum;                         //Number of Hard Disk
#     BYTE byDVRType;                         //DVR Type,  1: DVR 2: ATM DVR 3: DVS ......
#     BYTE byChanNum;                         //Number of Analog Channel
#     BYTE byStartChan;                     //The first Channel No. E.g. DVS- 1, DVR- 1
#     BYTE byAudioChanNum;                 //Number of Audio Channel
#     BYTE byIPChanNum;                     //Maximum number of IP Channel  low
#     BYTE byZeroChanNum;             //Zero channel encoding number//2010- 01- 16
#     BYTE byMainProto;             //Main stream transmission protocol 0- private,  1- rtsp,2-both private and rtsp
#     BYTE bySubProto;                 //Sub stream transmission protocol 0- private,  1- rtsp,2-both private and rtsp
#     BYTE bySupport;         //Ability, the 'AND' result by bit: 0- not support;  1- support
#     //bySupport & 0x1,  smart search
#     //bySupport & 0x2,  backup
#     //bySupport & 0x4,  get compression configuration ability
#     //bySupport & 0x8,  multi network adapter
#     //bySupport & 0x10, support remote SADP
#     //bySupport & 0x20  support Raid card
#     // bySupport & 0x40 support IPSAN directory search
#     BYTE bySupport1;        // Ability expand, the 'AND' result by bit: 0- not support;  1- support
#     // bySupport1 & 0x1, support snmp v30
#     // bySupport1& 0x2,support distinguish download and playback
#     //bySupport1 & 0x4, support deployment level
#     //bySupport1 & 0x8, support vca alarm time extension 
#     //bySupport1 & 0x10, support muti disks(more than 33)
#     //bySupport1 & 0x20, support rtsp over http
#     //bySupport1 & 0x40, support delay preview
#     //bySuppory1 & 0x80 support NET_DVR_IPPARACFG_V40, in addition  support  License plate of the new alarm information
#     BYTE bySupport2;        // Ability expand, the 'AND' result by bit: 0- not support;  1- support
#     //bySupport & 0x1, decoder support get stream by URL
#     //bySupport2 & 0x2,  support FTPV40
#     //bySupport2 & 0x4,  support ANR
#     //bySupport2 & 0x20, support get single item of device status
#     //bySupport2 & 0x40,  support stream encryt
#     WORD wDevType;              //device type
#     BYTE bySupport3;        //Support  epresent by bit, 0 - not support 1 - support 
#     //bySupport3 & 0x1- support batch config stream compress  
#     //bySupport3 & 0x8  support use delay preview parameter when delay preview
#     //bySupport3 & 0x10 support the interface of getting alarmhost main status V40
#     BYTE byMultiStreamProto;//support multi stream, represent by bit, 0-not support ;1- support; bit1-stream 3 ;bit2-stream 4, bit7-main stream, bit8-sub stream
#     BYTE byStartDChan;        //Start digital channel
#     BYTE byStartDTalkChan;    //Start digital talk channel
#     BYTE byHighDChanNum;        //Digital channel number high
#     BYTE bySupport4;        //Support  epresent by bit, 0 - not support 1 - support
#     //bySupport4 0x02 whether support NetSDK(NET_DVR_STDXMLConfig) tranfer form data
#     //bySupport4 & 0x4 whether support video wall unified interface
#     // bySupport4 & 0x80 Support device upload center alarm enable
#     BYTE byLanguageType;    // support language type by bit,0-support,1-not support  
#     //  byLanguageType 0 -old device
#     //  byLanguageType & 0x1 support chinese
#     //  byLanguageType & 0x2 support english
#     BYTE byVoiceInChanNum;   //voice in chan num 
#     BYTE byStartVoiceInChanNo; //start voice in chan num
#     BYTE  bySupport5;  //0-no support,1-support,bit0-muti stream
#     //bySupport5 &0x01support wEventTypeEx 
#     //bySupport5 &0x04support sence expend
#     BYTE  bySupport6;
#     BYTE  byMirrorChanNum;    //mirror channel num,<it represents direct channel in the recording host>
#     WORD  wStartMirrorChanNo;  //start mirror chan
#     BYTE bySupport7;        //Support  epresent by bit, 0 - not support 1 - support 
#     //bySupport7 & 0x1- supports INTER_VCA_RULECFG_V42 extension    
#     // bySupport7 & 0x2  Supports HVT IPC mode expansion
#     // bySupport7 & 0x04  Back lock time
#     // bySupport7 & 0x08  Set the pan PTZ position, whether to support the band channel
#     // bySupport7 & 0x10  Support for dual system upgrade backup
#     // bySupport7 & 0x20  Support OSD character overlay V50
#     // bySupport7 & 0x40  Support master slave tracking (slave camera)
#     // bySupport7 & 0x80  Support message encryption 
#     BYTE  byRes2;
# }NET_DVR_DEVICEINFO_V30, *LPNET_DVR_DEVICEINFO_V30;
class NET_DVR_DEVICEINFO_V30(c.Structure): pass
NET_DVR_DEVICEINFO_V30._fields_ = [
    ('sSerialNumber', BYTE*SERIALNO_LEN),
    ('byAlarmInPortNum', BYTE),
    ('byAlarmOutPortNum', BYTE),
    ('byDiskNum', BYTE),
    ('byDVRType', BYTE),
    ('byChanNum', BYTE),
    ('byStartChan', BYTE),
    ('byAudioChanNum', BYTE),
    ('byIPChanNum', BYTE),
    ('byZeroChanNum', BYTE),
    ('byMainProto', BYTE),
    ('bySubProto', BYTE),
    ('bySupport', BYTE),
    ('bySupport1', BYTE),
    ('bySupport2', BYTE),
    ('wDevType', WORD),
    ('bySupport3', BYTE),
    ('byMultiStreamProto', BYTE),
    ('byStartDChan', BYTE),
    ('byStartDTalkChan', BYTE),
    ('byHighDChanNum', BYTE),
    ('bySupport4', BYTE),
    ('byLanguageType', BYTE),
    ('byVoiceInChanNum', BYTE),
    ('byStartVoiceInChanNo', BYTE),
    ('bySupport5', BYTE),
    ('bySupport6', BYTE),
    ('byMirrorChanNum', BYTE),
    ('wStartMirrorChanNo', WORD),
    ('bySupport7', BYTE),
    ('byRes2', BYTE)
]
LPNET_DVR_DEVICEINFO_V30 = c.POINTER(NET_DVR_DEVICEINFO_V30)

# typedef void (CALLBACK *fLoginResultCallBack) (LONG lUserID, DWORD dwResult, LPNET_DVR_DEVICEINFO_V30 lpDeviceInfo, void* pUser);
fLoginResultCallBack = c.CFUNCTYPE(None, LONG, DWORD, LPNET_DVR_DEVICEINFO_V30, c.c_void_p)

# #define NET_DVR_DEV_ADDRESS_MAX_LEN 129
# #define NET_DVR_LOGIN_USERNAME_MAX_LEN 64
# #define NET_DVR_LOGIN_PASSWD_MAX_LEN 64

# typedef struct
# {
#     char sDeviceAddress[NET_DVR_DEV_ADDRESS_MAX_LEN];
#     BYTE byUseTransport;
#     WORD wPort;
#     char sUserName[NET_DVR_LOGIN_USERNAME_MAX_LEN];
#     char sPassword[NET_DVR_LOGIN_PASSWD_MAX_LEN];
#     fLoginResultCallBack cbLoginResult;
#     void *pUser;
#     BOOL bUseAsynLogin;
#     BYTE byProxyType;
#     BYTE byUseUTCTime;
#     BYTE byLoginMode; //0-Private 1-ISAPI 2-adapt
#     BYTE byHttps;     //0-tcp,1-tls 2-adapt
#     LONG iProxyID;
#     BYTE byVerifyMode;  
#     BYTE byRes3[119];
# }NET_DVR_USER_LOGIN_INFO, *LPNET_DVR_USER_LOGIN_INFO;


NET_DVR_DEV_ADDRESS_MAX_LEN = 129
NET_DVR_LOGIN_USERNAME_MAX_LEN = 64
NET_DVR_LOGIN_PASSWD_MAX_LEN = 64

class NET_DVR_USER_LOGIN_INFO(c.Structure): pass
NET_DVR_USER_LOGIN_INFO._fields_ = [
    ('sDeviceAddress', c.c_char*NET_DVR_DEV_ADDRESS_MAX_LEN),
    ('byUseTransport', BYTE),
    ('wPort', WORD),
    ('sUserName', c.c_char*NET_DVR_LOGIN_USERNAME_MAX_LEN),
    ('sPassword', c.c_char*NET_DVR_LOGIN_PASSWD_MAX_LEN),
    ('cbLoginResult', fLoginResultCallBack),
    ('pUser', c.c_void_p),
    ('bUseAsynLogin', BOOL),
    ('byProxyType', BYTE),
    ('byUseUTCTime', BYTE),
    ('byLoginMode', BYTE), # 0-Private 1-ISAPI 2-adapt
    ('byHttps', BYTE), # 0-tcp,1-tls 2-adapt
    ('iProxyID', LONG),
    ('byVerifyMode', BYTE),
    ('byRes3', BYTE*119)
]
LPNET_DVR_USER_LOGIN_INFO = c.POINTER(NET_DVR_USER_LOGIN_INFO)

#==============================================================================
# typedef struct tagNET_DVR_DEVICEINFO_V40
# {
#     NET_DVR_DEVICEINFO_V30 struDeviceV30;
#     BYTE  bySupportLock;        //the device support lock function,this byte assigned by SDK.when bySupportLock is 1,dwSurplusLockTime and byRetryLoginTime is valid 
#     BYTE  byRetryLoginTime;        //retry login times
#     BYTE  byPasswordLevel;      //PasswordLevel,0-invalid,1-default password,2-valid password,3-risk password,
#     //4- the administrator creates an ordinary user to set the password for him/her, and the ordinary user shall be prompted to "please modify the initial login password" after correctly logging into the device. In the case of no modification, the user will be reminded every time he/she logs in; 
#     //5- when the password of an ordinary user is modified by the administrator, the ordinary user needs to be prompted "please reset the login password" after correctly logging into the device again. If the password is not modified, the user will be reminded of each login;
#     //6- the administrator creates an installer/operator user and sets password for him/her,  then need prompt "please change initial password" after the user login in the device. If the password is not modified, it can't operate other actions except for changing password
#     BYTE  byProxyType;  //Proxy Type,0-not use proxy, 1-use socks5 proxy, 2-use EHome proxy
#     DWORD dwSurplusLockTime;    //surplus locked time
#     BYTE  byCharEncodeType;     //character encode type
#     BYTE  bySupportDev5;//Support v50 version of the device parameters, device name and device type name length is extended to 64 bytes 
#     BYTE  bySupport;  // capability set extension, bit and result: 0- no support, 1- support
#     // bySupport & 0x1:0 - Reserved
#     // bySupport & 0x2:0 - does not support changes to report 1- support change escalation
#     BYTE  byLoginMode; //loginmodel 0-Private 1-ISAPI
#     DWORD dwOEMCode;
#     int iResidualValidity;
#     BYTE  byResidualValidity;
#     BYTE  bySingleStartDTalkChan;
#     BYTE  bySingleDTalkChanNums;
#     BYTE  byPassWordResetLevel;
#     BYTE  bySupportStreamEncrypt;
#     BYTE  byMarketType;
#     BYTE  byRes2[238];
# }NET_DVR_DEVICEINFO_V40, *LPNET_DVR_DEVICEINFO_V40;
class NET_DVR_DEVICEINFO_V40(c.Structure): pass
NET_DVR_DEVICEINFO_V40._fields_ = [
    ('struDeviceV30', NET_DVR_DEVICEINFO_V30),
    ('bySupportLock', BYTE),
    ('byRetryLoginTime', BYTE),
    ('byPasswordLevel', BYTE),
    ('byProxyType', BYTE),
    ('dwSurplusLockTime', DWORD),
    ('byCharEncodeType', BYTE),
    ('bySupportDev5', BYTE),
    ('bySupport', BYTE),
    ('byLoginMode', BYTE),
    ('dwOEMCode', DWORD),
    ('iResidualValidity', c.c_int),
    ('byResidualValidity', BYTE),
    ('bySingleStartDTalkChan', BYTE),
    ('bySingleDTalkChanNums', BYTE),
    ('byPassWordResetLevel', BYTE),
    ('bySupportStreamEncrypt', BYTE),
    ('byMarketType', BYTE),
    ('byRes2', BYTE*238),
]
LPNET_DVR_DEVICEINFO_V40 = c.POINTER(NET_DVR_DEVICEINFO_V40)

#==============================================================================
# NET_DVR_API LONG __stdcall NET_DVR_Login_V40(LPNET_DVR_USER_LOGIN_INFO pLoginInfo,LPNET_DVR_DEVICEINFO_V40 lpDeviceInfo);
NET_DVR_Login_V40 = libhcnetsdk.NET_DVR_Login_V40
NET_DVR_Login_V40.argtypes = [LPNET_DVR_USER_LOGIN_INFO, LPNET_DVR_DEVICEINFO_V40]
NET_DVR_Login_V40.restype = LONG

#==============================================================================
# NET_DVR_API BOOL __stdcall NET_DVR_Logout(LONG lUserID);
NET_DVR_Logout = libhcnetsdk.NET_DVR_Logout
NET_DVR_Logout.argtypes = [LONG]
NET_DVR_Logout.restype = BOOL

#==============================================================================
# typedef struct
# {
#     DWORD dwYear;             //Year
#     DWORD dwMonth;             //Month
#     DWORD dwDay;             //Day
#     DWORD dwHour;             //Hour
#     DWORD dwMinute;         //Minute
#     DWORD dwSecond;         //Second
# }NET_DVR_TIME, *LPNET_DVR_TIME;
class NET_DVR_TIME(c.Structure):
    _fields_ = [
        ('dwYear', DWORD),
        ('dwMonth', DWORD),
        ('dwDay', DWORD),
        ('dwHour', DWORD),
        ('dwMinute', DWORD),
        ('dwSecond', DWORD)
    ]

    @staticmethod
    def from_datetime(dt):
        t = NET_DVR_TIME()
        t.dwYear = dt.year
        t.dwMonth = dt.month
        t.dwDay = dt.day
        t.dwHour = dt.hour
        t.dwMinute = dt.minute
        t.dwSecond = dt.second
        return t
    
    def as_datetime(self):
        dt = datetime.datetime(
            self.dwYear,
            self.dwMonth,
            self.dwDay,
            self.dwHour,
            self.dwMinute,
            self.dwSecond
        )
        return dt
    
LPNET_DVR_TIME = c.POINTER(NET_DVR_TIME)


#==============================================================================
# typedef struct tagNET_DVR_RECORD_TIME_SPAN_INQUIRY
# {
#     DWORD    dwSize;    //Structure size
#     BYTE    byType;    //0- normal audio and video recording, 1- picture channel recording, 
#     //2- ANR channel recording, 3- frame extracting channel recording
#     BYTE     byRes[63]; //Reserved
# }NET_DVR_RECORD_TIME_SPAN_INQUIRY, *LPNET_DVR_RECORD_TIME_SPAN_INQUIRY;
class NET_DVR_RECORD_TIME_SPAN_INQUIRY(c.Structure):
    _fields_ = [
        ('dwSize', DWORD),
        ('byType', BYTE),
        ('byRes', BYTE*63)
    ]
LPNET_DVR_RECORD_TIME_SPAN_INQUIRY = c.POINTER(NET_DVR_RECORD_TIME_SPAN_INQUIRY)


#==============================================================================
# typedef struct tagNET_DVR_RECORD_TIME_SPAN
# {
#     DWORD          dwSize;        //Structure size
#     NET_DVR_TIME  strBeginTime;  //Start time
#     NET_DVR_TIME  strEndTime;    //End time
#     BYTE          byType;        //0- normal audio and video recording, 1- picture channel recording, 
#     //2- ANR channel recording, 3- frame extracting channel recording
#     BYTE           byRes[35];     //Reserved
# }NET_DVR_RECORD_TIME_SPAN, *LPNET_DVR_RECORD_TIME_SPAN;
class NET_DVR_RECORD_TIME_SPAN(c.Structure):
    _fields_ = [
        ('dwSize', DWORD),
        ('strBeginTime', NET_DVR_TIME),
        ('strEndTime', NET_DVR_TIME),
        ('byType', BYTE),
        ('byRes', BYTE*35)
    ]
LPNET_DVR_RECORD_TIME_SPAN = c.POINTER(NET_DVR_RECORD_TIME_SPAN)


#==============================================================================
# NET_DVR_API BOOL __stdcall NET_DVR_InquiryRecordTimeSpan(LONG lUserID, DWORD dwChannel,  NET_DVR_RECORD_TIME_SPAN_INQUIRY const *lpInquiry, LPNET_DVR_RECORD_TIME_SPAN lpResult);
NET_DVR_InquiryRecordTimeSpan = libhcnetsdk.NET_DVR_InquiryRecordTimeSpan
NET_DVR_InquiryRecordTimeSpan.argtypes = [LONG, DWORD, LPNET_DVR_RECORD_TIME_SPAN_INQUIRY, LPNET_DVR_RECORD_TIME_SPAN]
NET_DVR_InquiryRecordTimeSpan.restype = BOOL


#==============================================================================
# NET_DVR_API LONG __stdcall NET_DVR_FindFile(LONG lUserID, LONG lChannel,DWORD dwFileType, LPNET_DVR_TIME lpStartTime, LPNET_DVR_TIME lpStopTime);
# 0xff- all, 0-continuous recording, 1- motion detection, 2- alarm recording, 3- motion detection | alarm, 4-motion detection & alarm, 5-command trigger, 6- manual recording, 7-VCA recording, 10-PIR alarm, 11-wireless alarm, 12-panic alarm, 13-all, 14-intelligent traffic events, 15-line crossing, 16-intrusion, 17-sound exception, 18-scene change, 19-line crossing|intrusion|face detection|sound exception|scene change, 20-face detection, 21-sensor, 22-callback, 23-copy back recording, 24-video tampering, 25-POS recording, 26-region entrance, 27-region exiting, 28-loitering detection, 29-people gathering, 30-fast moving, 31-parking detection, 32-unattended baggage, 33-object removal, 34-fire source detection, 35-tampering detection, 36-ship detection, 37-temperature pre-alarm, 38-temperature alarm, 39-fight detection, 40-getting up detection, 41-sleepy detetion, 42-temperature difference alarm, 43-offline temperature measurement alarm, 44-zone alarm, 45-panic alarm, 46-inquiry service, 47-getting up detection, 48-climbing detection, 49-in-toilet overtime, 50-running detetion, 51-playground overstay detection
NET_DVR_FindFile = libhcnetsdk.NET_DVR_FindFile
NET_DVR_FindFile.argtypes = [LONG, LONG, DWORD, LPNET_DVR_TIME, LPNET_DVR_TIME]
NET_DVR_FindFile.restype = LONG


#==============================================================================
# typedef struct
# {
#     char sFileName[100]; // File Name
#     NET_DVR_TIME struStartTime; //Start time of the file
#     NET_DVR_TIME struStopTime; //End time of the file
#     DWORD dwFileSize; //File size
# }NET_DVR_FIND_DATA, *LPNET_DVR_FIND_DATA;
class NET_DVR_FIND_DATA(c.Structure):
    _fields_ = [
        ('sFileName', c.c_char*100),
        ('struStartTime', NET_DVR_TIME),
        ('struStopTime', NET_DVR_TIME),
        ('dwFileSize', DWORD)
    ]
LPNET_DVR_FIND_DATA = c.POINTER(NET_DVR_FIND_DATA)


#==============================================================================
# NET_DVR_API LONG __stdcall NET_DVR_FindNextFile(LONG lFindHandle,LPNET_DVR_FIND_DATA lpFindData);
NET_DVR_FindNextFile = libhcnetsdk.NET_DVR_FindNextFile
NET_DVR_FindNextFile.argtypes = [LONG, LPNET_DVR_FIND_DATA]
NET_DVR_FindNextFile.restype = LONG


#==============================================================================
# NET_DVR_API BOOL __stdcall NET_DVR_FindClose(LONG lFindHandle);
NET_DVR_FindClose = libhcnetsdk.NET_DVR_FindClose
NET_DVR_FindClose.argtypes = [LONG]
NET_DVR_FindClose.restype = BOOL


#==============================================================================
# NET_DVR_API DWORD __stdcall NET_DVR_GetLastError();
NET_DVR_GetLastError = libhcnetsdk.NET_DVR_GetLastError
# NET_DVR_GetLastError.argtypes = 
NET_DVR_GetLastError.restype = DWORD


STREAM_ID_LEN   = 32

#==============================================================================
# typedef struct tagNET_DVR_STREAM_INFO
# {
#     DWORD dwSize;
#     BYTE  byID[STREAM_ID_LEN];      //ID
#     DWORD dwChannel;                //Relation channel, 0xffffffff: not related
#     BYTE  byRes[32];
# }NET_DVR_STREAM_INFO, *LPNET_DVR_STREAM_INFO;
class NET_DVR_STREAM_INFO(c.Structure):
    _fields_ = [
        ('dwSize', DWORD),
        ('byID', BYTE*STREAM_ID_LEN),
        ('dwChannel', DWORD),
        ('byRes', BYTE*32)
    ]
LPNET_DVR_STREAM_INFO = c.POINTER(NET_DVR_STREAM_INFO)

#==============================================================================
# typedef struct tagNET_DVR_VOD_PARA
# {
#     DWORD                dwSize;
#     NET_DVR_STREAM_INFO struIDInfo;
#     NET_DVR_TIME        struBeginTime;
#     NET_DVR_TIME        struEndTime;
#     HWND                hWnd;
#     BYTE                byDrawFrame;
#     BYTE                byVolumeType;  //0-common volume   1-backup volme
#     BYTE                byVolumeNum;  //backup volme number
#     BYTE                byStreamType;
#     DWORD                   dwFileIndex;      //file index
#     BYTE                byAudioFile;
#     BYTE                byCourseFile;    //Course file 0 - no, 1 - yes
#     BYTE                byDownload;    //Download 0- no, 1- yes.
#     BYTE                byOptimalStreamType;  //Whether to play back according to the optimal code stream type. 0 - no, 1 - yes
#     BYTE                byUseAsyn;       //0-SynIO��1-AsynIO 
#     BYTE                byRes2[19];
# }NET_DVR_VOD_PARA, *LPNET_DVR_VOD_PARA;
class NET_DVR_VOD_PARA(c.Structure): pass
NET_DVR_VOD_PARA._fields_ = [
    ('dwSize', DWORD),
    ('struIDInfo', NET_DVR_STREAM_INFO),
    ('struBeginTime', NET_DVR_TIME),
    ('struEndTime', NET_DVR_TIME),
    ('hWnd', HWND),
    ('byDrawFrame', BYTE),
    ('byVolumeType', BYTE),
    ('byVolumeNum', BYTE),
    ('byStreamType', BYTE),
    ('dwFileIndex', DWORD),
    ('byAudioFile', BYTE),
    ('byCourseFile', BYTE),
    ('byDownload', BYTE),
    ('byOptimalStreamType', BYTE),
    ('byUseAsyn', BYTE),
    ('byRes2', BYTE*19)
]
LPNET_DVR_VOD_PARA = c.POINTER(NET_DVR_VOD_PARA)


#==============================================================================
# NET_DVR_API LONG __stdcall NET_DVR_PlayBackByTime(LONG lUserID,LONG lChannel, LPNET_DVR_TIME lpStartTime, LPNET_DVR_TIME lpStopTime, HWND hWnd);
NET_DVR_PlayBackByTime = libhcnetsdk.NET_DVR_PlayBackByTime
NET_DVR_PlayBackByTime.argtypes = [LONG, LONG, LPNET_DVR_TIME, LPNET_DVR_TIME, HWND]
NET_DVR_PlayBackByTime.restype = LONG


#==============================================================================
# NET_DVR_API LONG __stdcall NET_DVR_PlayBackByTime_V40(LONG lUserID, NET_DVR_VOD_PARA const* pVodPara);
NET_DVR_PlayBackByTime_V40 = libhcnetsdk.NET_DVR_PlayBackByTime_V40
NET_DVR_PlayBackByTime_V40.argtypes = [LONG, LPNET_DVR_VOD_PARA]
NET_DVR_PlayBackByTime_V40.restype = LONG


#==============================================================================
# NET_DVR_API BOOL __stdcall NET_DVR_StopPlayBack(LONG lPlayHandle);
NET_DVR_StopPlayBack = libhcnetsdk.NET_DVR_StopPlayBack
NET_DVR_StopPlayBack.argtypes = [LONG]
NET_DVR_StopPlayBack.restype = BOOL


# /********************Preview Callback Function*********************/
# dwDataType in fPlayDataCallBack
class PlayDataCallBack:
	NET_DVR_SYSHEAD =                     1  # System header
	NET_DVR_STREAMDATA =                  2  # stream data
	NET_DVR_AUDIOSTREAMDATA =             3  # Audio Stream data
	NET_DVR_STD_VIDEODATA =               4  # Standard video stream data
	NET_DVR_STD_AUDIODATA =               5  # Standard audio stream data
	NET_DVR_SDP =                         6  # SDP data(valid for rtsp protocol) 
	NET_DVR_CHANGE_FORWARD =             10  # stream change from reverse to forward  
	NET_DVR_CHANGE_REVERSE =             11  # stream change from forward to reverse
	NET_DVR_PLAYBACK_ALLFILEEND =        12  # Play back All File End
	NET_DVR_VOD_DRAW_FRAME =             13  # vod draw Frame
	NET_DVR_VOD_DRAW_DATA =              14  # vod drawing
	NET_DVR_HLS_INDEX_DATA =             15  # HLS data
	NET_DVR_PLAYBACK_NEW_POS =           16  # new pos
	NET_DVR_METADATA_DATA =             107  # Metadata
	NET_DVR_PRIVATE_DATA =              112 # Private data

#==============================================================================
# void(CALLBACK *fPlayDataCallBack) (LONG lPlayHandle, DWORD dwDataType, BYTE *pBuffer,DWORD dwBufSize,DWORD dwUser)
fPlayDataCallBack = c.CFUNCTYPE(None, LONG, DWORD, c.POINTER(BYTE), DWORD, DWORD)


#==============================================================================
# NET_DVR_API BOOL __stdcall NET_DVR_SetPlayDataCallBack(LONG lPlayHandle,void(CALLBACK *fPlayDataCallBack) (LONG lPlayHandle, DWORD dwDataType, BYTE *pBuffer,DWORD dwBufSize,DWORD dwUser),DWORD dwUser);
NET_DVR_SetPlayDataCallBack = libhcnetsdk.NET_DVR_SetPlayDataCallBack
NET_DVR_SetPlayDataCallBack.argtypes = [LONG, fPlayDataCallBack, DWORD]
NET_DVR_SetPlayDataCallBack.restype = BOOL


#==============================================================================
# void(CALLBACK *fPlayDataCallBack_V40) (LONG lPlayHandle, DWORD dwDataType, BYTE *pBuffer,DWORD dwBufSize,void *pUser)
fPlayDataCallBack_V40 = c.CFUNCTYPE(None, LONG, DWORD, c.POINTER(BYTE), DWORD, c.c_void_p)


#==============================================================================
# NET_DVR_API BOOL __stdcall NET_DVR_SetPlayDataCallBack_V40(LONG lPlayHandle,void(CALLBACK *fPlayDataCallBack_V40) (LONG lPlayHandle, DWORD dwDataType, BYTE *pBuffer,DWORD dwBufSize,void *pUser),void *pUser);
NET_DVR_SetPlayDataCallBack_V40 = libhcnetsdk.NET_DVR_SetPlayDataCallBack_V40
NET_DVR_SetPlayDataCallBack_V40.argtypes = [LONG, fPlayDataCallBack_V40, c.c_void_p]
NET_DVR_SetPlayDataCallBack_V40.restype = BOOL


#==============================================================================
# /*************************************************
# Play Control Commands
# Macro Definition
# NET_DVR_PlayBackControl
# NET_DVR_PlayControlLocDisplay
# NET_DVR_DecPlayBackCtrl
# **************************************************/
class PlayBackControl:
    NET_DVR_PLAYSTART =             1  # Start Play
    NET_DVR_PLAYSTOP =              2  # Stop Play
    NET_DVR_PLAYPAUSE =             3  # Pause Play
    NET_DVR_PLAYRESTART =           4  # Restore Play
    NET_DVR_PLAYFAST =              5  # Play faster
    NET_DVR_PLAYSLOW =              6  # Play slower
    NET_DVR_PLAYNORMAL =            7  # Normal Speed
    NET_DVR_PLAYFRAME =             8  # Play frame by frame
    NET_DVR_PLAYSTARTAUDIO =        9  # Open audio
    NET_DVR_PLAYSTOPAUDIO =         10 # Close audio
    NET_DVR_PLAYAUDIOVOLUME =       11 # Adjust volume 
    NET_DVR_PLAYSETPOS =            12 # Change the playback progress 
    NET_DVR_PLAYGETPOS =            13 # Get the playback progress
    NET_DVR_PLAYGETTIME =           14 # Get the played time (available when playback by time) 
    NET_DVR_PLAYGETFRAME =          15 # Get the played frame number (available when playback by file) 
    NET_DVR_GETTOTALFRAMES =        16 # Get total frame number of current file (available when playback by file) 
    NET_DVR_GETTOTALTIME =          17 # Get total time of current file (available when playback by file) 
    NET_DVR_THROWBFRAME =           20 # Discard B frame
    NET_DVR_SETSPEED =              24 # Setup stream speed
    NET_DVR_KEEPALIVE =             25 # Keep connection with server (if callback is blocked,  send it every 2 second) 
    NET_DVR_PLAYSETTIME =           26 # Set playback position according to absolute time 
    NET_DVR_PLAYGETTOTALLEN =       27 # Get total time length of all the detected files under playback by time mode
    NET_DVR_PLAYSETTIME_V50 =       28 # Set playback position according to absolute time (support time zone)
    NET_DVR_PLAY_FORWARD =          29 # change stream from reverse to forward
    NET_DVR_PLAY_REVERSE =          30 # change stream from froward to reverse
    NET_DVR_SET_DECODEFFRAMETYPE =  31 # Set decode frame type
    NET_DVR_SET_TRANS_TYPE =        32 # Set Transcodeing Type 
    NET_DVR_PLAY_CONVERT =          33 # playback decode
    NET_DVR_START_DRAWFRAME =       34 # start draw I Frame 
    NET_DVR_STOP_DRAWFRAME =        35 # stop draw I Frame
    NET_DVR_CHANGEWNDRESOLUTION =   36 # change wnd size
    NET_DVR_RESETBUFFER =            37 # reset matrix decode buffer(remote playback file)
    NET_DVR_VOD_DRAG_ING =          38 # playback in drag 
    NET_DVR_VOD_DRAG_END =          39 # end of the playback drag 
    NET_DVR_VOD_RESET_PLAYTIME =    40 # reset playback time


#==============================================================================
# NET_DVR_API BOOL __stdcall NET_DVR_PlayBackControl(LONG lPlayHandle,DWORD dwControlCode,DWORD dwInValue,DWORD *LPOutValue);
NET_DVR_PlayBackControl = libhcnetsdk.NET_DVR_PlayBackControl
NET_DVR_PlayBackControl.argtypes = [LONG, DWORD, DWORD, c.POINTER(DWORD)]
NET_DVR_PlayBackControl.restype = BOOL

#==============================================================================
# NET_DVR_API BOOL __stdcall NET_DVR_PlayBackControl_V40(LONG lPlayHandle,DWORD dwControlCode, LPVOID lpInBuffer = NULL, DWORD dwInLen = 0, LPVOID lpOutBuffer = NULL, DWORD *lpOutLen = NULL);
NET_DVR_PlayBackControl_V40 = libhcnetsdk.NET_DVR_PlayBackControl_V40
NET_DVR_PlayBackControl_V40.argtypes = [LONG, DWORD, LPVOID, DWORD, LPVOID, DWORD]
NET_DVR_PlayBackControl_V40.restype = BOOL


#==============================================================================
# typedef struct tagNET_DVR_PACKET_INFO_EX
# {
#     WORD     wWidth;         //width
#     WORD     wHeight;        //height
#     DWORD    dwTimeStamp;    //lower time stamp
#     DWORD    dwTimeStampHigh;//higher time stamp 
#     DWORD    dwYear;            //year
#     DWORD    dwMonth;         //month
#     DWORD    dwDay;           //day
#     DWORD    dwHour;          //hour
#     DWORD    dwMinute;        //minute
#     DWORD    dwSecond;        //second
#     DWORD    dwMillisecond;   //millisecond
#     DWORD    dwFrameNum;     //frame num
#     DWORD    dwFrameRate;    //frame rate
#     DWORD    dwFlag;         //flag E
#     DWORD    dwFilePos;      //file pos
#     DWORD     dwPacketType;    //packet type:0 -file head,1 -video I frame,2- video B frame, 3- video P frame, 10- audio packet, 11- private packet
#     DWORD     dwPacketSize;   //packet size
#     unsigned char*    pPacketBuffer;  //packet buffer
#     BYTE     byRes1[4];
#     DWORD    dwPacketMode;   // Packet Mode:0-Res,1-FU_A
#     BYTE     byRes2[16];
#     DWORD    dwReserved[6];    //reserved[0] Private data type 
#     //reserved[1] Private bare data high address
#     //reserved[2]Private bare data low address
#     //reserved[3] Private bare data length
#     //reserved[4] Private frame / packet time interval \ \ time stamp
#     //reserved[5].bitIs a deep P frame,deepP:1,not deepP:0;     lizhonghu 20150203
# }NET_DVR_PACKET_INFO_EX, *LPNET_DVR_PACKET_INFO_EX;
class NET_DVR_PACKET_INFO_EX(c.Structure): 
    _fields_ = [
        ('wWidth', WORD),
        ('wHeight', WORD),
        ('dwTimeStamp', DWORD),
        ('dwTimeStampHigh', DWORD),
        ('dwYear', DWORD),
        ('dwMonth', DWORD),
        ('dwDay', DWORD),
        ('dwHour', DWORD),
        ('dwMinute', DWORD),
        ('dwSecond', DWORD),
        ('dwMillisecond', DWORD),
        ('dwFrameNum', DWORD),
        ('dwFrameRate', DWORD),
        ('dwFlag', DWORD),
        ('dwFilePos', DWORD),
        ('dwPacketType', DWORD),
        ('dwPacketSize', DWORD),
        ('pPacketBuffer', c.POINTER(BYTE)),
        ('byRes1', BYTE*4),
        ('dwPacketMode', DWORD),
        ('byRes2', BYTE*16),
        ('dwReserved', DWORD*6),
    ]
LPNET_DVR_PACKET_INFO_EX = c.POINTER(NET_DVR_PACKET_INFO_EX)


#==============================================================================
# void (CALLBACK *fPlayESCallBack)(LONG lPlayHandle, NET_DVR_PACKET_INFO_EX *struPackInfo,  void* pUser)
fPlayESCallBack = c.CFUNCTYPE(None, LONG, LPNET_DVR_PACKET_INFO_EX, c.c_void_p)


#==============================================================================
# NET_DVR_API BOOL __stdcall NET_DVR_SetPlayBackESCallBack(LONG lPlayHandle, void (CALLBACK *fPlayESCallBack)(LONG lPlayHandle, NET_DVR_PACKET_INFO_EX *struPackInfo,  void* pUser), void* pUser);
NET_DVR_SetPlayBackESCallBack = libhcnetsdk.NET_DVR_SetPlayBackESCallBack
NET_DVR_SetPlayBackESCallBack.argtypes = [LONG, fPlayESCallBack, LPVOID]
NET_DVR_SetPlayBackESCallBack.restype = BOOL

#==============================================================================
# NET_DVR_API BOOL __stdcall NET_DVR_SetConnectTime(DWORD dwWaitTime = 3000, DWORD dwTryTimes = 3);
NET_DVR_SetConnectTime = libhcnetsdk.NET_DVR_SetConnectTime
NET_DVR_SetConnectTime.argtypes = [DWORD, DWORD]
NET_DVR_SetConnectTime.restype = BOOL

#==============================================================================
# NET_DVR_API BOOL  __stdcall NET_DVR_SetRecvTimeOut(DWORD nRecvTimeOut = 5000); 
NET_DVR_SetRecvTimeOut = libhcnetsdk.NET_DVR_SetRecvTimeOut
NET_DVR_SetRecvTimeOut.argtypes = [DWORD]
NET_DVR_SetRecvTimeOut.restype = BOOL
