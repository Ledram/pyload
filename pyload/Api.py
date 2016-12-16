# -*- coding: utf-8 -*-
#@author: RaNaN

from __future__ import absolute_import
from __future__ import unicode_literals
from builtins import str
from builtins import object
import re
from types import MethodType

from .remote.apitypes import *

# contains function names mapped to their permissions
# unlisted functions are for admins only
perm_map = {}

# decorator only called on init, never initialized, so has no effect on runtime
def require_perm(bits):
    class _Dec(object):
        def __new__(cls, func, *args, **kwargs):
            perm_map[func.__name__] = bits
            return func
    return _Dec

urlmatcher = re.compile(r"((https?|ftps?|xdcc|sftp):((//)|(\\\\))+[\w\d:#@%/;$()~_?\+\-=\\\.&]*)", re.IGNORECASE)

stateMap = {
    DownloadState.All: frozenset(getattr(DownloadStatus, x) for x in dir(DownloadStatus) if not x.startswith("_")),
    DownloadState.Finished: frozenset((DownloadStatus.Finished, DownloadStatus.Skipped)),
    DownloadState.Unfinished: None, # set below
    DownloadState.Failed: frozenset((DownloadStatus.Failed, DownloadStatus.TempOffline, DownloadStatus.Aborted,
                                     DownloadStatus.NotPossible, DownloadStatus.FileMismatch)),
    DownloadState.Unmanaged: None, #TODO
}

stateMap[DownloadState.Unfinished] = frozenset(stateMap[DownloadState.All].difference(stateMap[DownloadState.Finished]))

def state_string(state):
    return ",".join(str(x) for x in stateMap[state])

from .datatypes.user import User


class Api(Iface):
    """
    **pyLoads API**

    This is accessible either internal via core.api, websocket backend or json api.

    see Thrift specification file remote/thriftbackend/pyload.thrift\
    for information about data structures and what methods are usable with rpc.

    Most methods requires specific permissions, please look at the source code if you need to know.\
    These can be configured via web interface.
    Admin user have all permissions, and are the only ones who can access the methods with no specific permission.
    """

    EXTERNAL = Iface  # let the json api know which methods are external
    EXTEND = False  # only extendable when set too true

    def __init__(self, core):
        self.pyload = core
        self.user_apis = {}

    @property
    def user(self):
        return None #TODO return default user?

    @property
    def primary_uid(self):
        return self.user.primary if self.user else None


    def has_access(self, obj):
        """ Helper method to determine if a user has access to a resource.
         Works for obj that provides .owner attribute. Core admin has always access."""
        return self.user is None or self.user.hasAccess(obj)

    @classmethod
    def init_components(cls):
        # Allow extending the api
        # This prevents unintentionally registering of the components,
        # but will only work once when they are imported
        cls.EXTEND = True
        # Import all Api modules, they register themselves.
        import pyload.api
        # they will vanish from the namespace afterwards


    @classmethod
    def extend(cls, api):
        """Takes all params from api and extends cls with it.
            api class can be removed afterwards

        :param api: Class with methods to extend
        """
        if cls.EXTEND:
            for name, func in api.__dict__.items():
                if name.startswith("_"): continue
                setattr(cls, name, MethodType(func, None, cls))

        return cls.EXTEND

    def with_user_context(self, uid):
        """ Returns a proxy version of the api, to call method in user context

        :param uid: user or userData instance or uid
        :return: :class:`UserApi`
        """
        if isinstance(uid, User):
            uid = uid.uid

        if uid not in self.user_apis:
            user = self.pyload.db.get_user_data(uid=uid)
            if not user: #TODO: anonymous user?
                return None

            self.user_apis[uid] = UserApi(self.pyload, User.fromUserData(self, user))

        return self.user_apis[uid]


    #############################
    #  Auth+User Information
    #############################

    @require_perm(Permission.All)
    def login(self, username, password, remoteip=None):
        """Login into pyLoad, this **must** be called when using rpc before any methods can be used.

        :param username:
        :param password:
        :param remoteip: Omit this argument, its only used internal
        :return: bool indicating login was successful
        """
        return True if self.checkAuth(username, password, remoteip) else False

    def check_auth(self, username, password, remoteip=None):
        """Check authentication and returns details

        :param username:
        :param password:
        :param remoteip:
        :return: dict with info, empty when login is incorrect
        """
        self.pyload.log.info(_("User '%s' tries to log in") % username)

        return self.pyload.db.check_auth(username, password)

    @staticmethod
    def is_authorized(func, user):
        """checks if the user is authorized for specific method

        :param func: function name
        :param user: `User`
        :return: boolean
        """
        if user.isAdmin():
            return True
        elif func in perm_map and user.hasPermission(perm_map[func]):
            return True
        else:
            return False


class UserApi(Api):
    """  Proxy object for api that provides all methods in user context """

    def __init__(self, core, user):
        # No need to init super class
        self.pyload = core
        self._user = user

    def with_user_context(self, uid):
        raise Exception("Not allowed")

    @property
    def user(self):
        return self._user
