# coding: utf-8

#------------------------------
# 计划任务
#------------------------------
import sys
import os
import json
# import psutil
import time

sys.path.append(os.getcwd() + "/class/")
reload(sys)
sys.setdefaultencoding('utf-8')
import db
import public


global pre, timeoutCount, logPath, isTask, oldEdate, isCheck
pre = 0
timeoutCount = 0
isCheck = 0
oldEdate = None
logPath = '/tmp/panelExec.log'
isTask = '/tmp/panelTask.pl'


class MyBad():
    _msg = None

    def __init__(self, msg):
        self._msg = msg

    def __repr__(self):
        return self._msg


def ExecShell(cmdstring, cwd=None, timeout=None, shell=True):
    try:
        global logPath
        import shlex
        import datetime
        import subprocess
        import time

        if timeout:
            end_time = datetime.datetime.now() + datetime.timedelta(seconds=timeout)

        sub = subprocess.Popen(cmdstring + ' > ' + logPath + ' 2>&1',
                               cwd=cwd, stdin=subprocess.PIPE, shell=shell, bufsize=4096)

        while sub.poll() is None:
            time.sleep(0.1)

        return sub.returncode
    except:
        return None


def DownloadFile(url, filename):
    # 下载文件
    try:
        import urllib
        import socket
        socket.setdefaulttimeout(10)
        urllib.urlretrieve(url, filename=filename, reporthook=DownloadHook)
        os.system('chown www.www ' + filename)
        WriteLogs('done')
    except:
        WriteLogs('done')


def DownloadHook(count, blockSize, totalSize):
    # 下载文件进度回调
    global pre
    used = count * blockSize
    pre1 = int((100.0 * used / totalSize))
    if pre == pre1:
        return
    speed = {'total': totalSize, 'used': used, 'pre': pre}
    WriteLogs(json.dumps(speed))
    pre = pre1


def WriteLogs(logMsg):
    # 写输出日志
    try:
        global logPath
        fp = open(logPath, 'w+')
        fp.write(logMsg)
        fp.close()
    except:
        pass


def startTask():
    # 任务队列
    global isTask
    # import time
    # import public
    try:
        while True:
            try:
                if os.path.exists(isTask):
                    sql = db.Sql()
                    sql.table('tasks').where(
                        "status=?", ('-1',)).setField('status', '0')
                    taskArr = sql.table('tasks').where("status=?", ('0',)).field(
                        'id,type,execstr').order("id asc").select()
                    for value in taskArr:
                        start = int(time.time())
                        if not sql.table('tasks').where("id=?", (value['id'],)).count():
                            continue
                        sql.table('tasks').where("id=?", (value['id'],)).save(
                            'status,start', ('-1', start))
                        if value['type'] == 'download':
                            argv = value['execstr'].split('|bt|')
                            DownloadFile(argv[0], argv[1])
                        elif value['type'] == 'execshell':
                            ExecShell(value['execstr'])
                        end = int(time.time())
                        sql.table('tasks').where("id=?", (value['id'],)).save(
                            'status,end', ('1', end))
                        if(sql.table('tasks').where("status=?", ('0')).count() < 1):
                            os.system('rm -f ' + isTask)
            except:
                pass
            siteEdate()
            mainSafe()
            time.sleep(2)
    except:
        time.sleep(60)
        startTask()


def mainSafe():
    global isCheck
    try:
        if isCheck < 100:
            isCheck += 1
            return True
        isCheck = 0
        isStart = public.ExecShell(
            "ps aux |grep 'python main.py'|grep -v grep|awk '{print $2}'")[0]
        if not isStart:
            os.system('/etc/init.d/bt start')
            isStart = public.ExecShell(
                "ps aux |grep 'python main.py'|grep -v grep|awk '{print $2}'")[0]
            public.WriteLog('守护程序', '面板服务程序启动成功 -> PID: ' + isStart)
    except:
        time.sleep(30)
        mainSafe()


def siteEdate():
    # 网站到期处理
    global oldEdate
    try:
        if not oldEdate:
            oldEdate = public.readFile('data/edate.pl')
        if not oldEdate:
            oldEdate = '0000-00-00'
        mEdate = time.strftime('%Y-%m-%d', time.localtime())
        if oldEdate == mEdate:
            return False
        edateSites = public.M('sites').where('edate>? AND edate<? AND (status=? OR status=?)',
                                             ('0000-00-00', mEdate, 1, u'正在运行')).field('id,name').select()
        import panelSite
        siteObject = panelSite.panelSite()
        for site in edateSites:
            get = MyBad('')
            get.id = site['id']
            get.name = site['name']
            siteObject.SiteStop(get)
        oldEdate = mEdate
        public.writeFile('data/edate.pl', mEdate)
    except:
        pass


def systemTask():
    # 系统监控任务
    try:
        import system
        import psutil
        import time
        sm = system.system()
        filename = 'data/control.conf'
        sql = db.Sql().dbfile('system')
        csql = '''CREATE TABLE IF NOT EXISTS `load_average` (
  `id` INTEGER PRIMARY KEY AUTOINCREMENT,
  `pro` REAL,
  `one` REAL,
  `five` REAL,
  `fifteen` REAL,
  `addtime` INTEGER
)'''
        sql.execute(csql, ())
        cpuIo = cpu = {}
        cpuCount = psutil.cpu_count()
        used = count = 0
        reloadNum = 0
        network_up = network_down = diskio_1 = diskio_2 = networkInfo = cpuInfo = diskInfo = None
        while True:
            if not os.path.exists(filename):
                time.sleep(10)
                continue

            day = 30
            try:
                day = int(public.readFile(filename))
                if day < 1:
                    time.sleep(10)
                    continue
            except:
                day = 30

            tmp = {}
            # 取当前CPU Io
            tmp['used'] = psutil.cpu_percent(interval=1)

            if not cpuInfo:
                tmp['mem'] = GetMemUsed()
                cpuInfo = tmp

            if cpuInfo['used'] < tmp['used']:
                tmp['mem'] = GetMemUsed()
                cpuInfo = tmp

            # 取当前网络Io
            networkIo = psutil.net_io_counters()[:4]
            if not network_up:
                network_up = networkIo[0]
                network_down = networkIo[1]
            tmp = {}
            tmp['upTotal'] = networkIo[0]
            tmp['downTotal'] = networkIo[1]
            tmp['up'] = round(float((networkIo[0] - network_up) / 1024), 2)
            tmp['down'] = round(float((networkIo[1] - network_down) / 1024), 2)
            tmp['downPackets'] = networkIo[3]
            tmp['upPackets'] = networkIo[2]

            network_up = networkIo[0]
            network_down = networkIo[1]

            if not networkInfo:
                networkInfo = tmp
            if (tmp['up'] + tmp['down']) > (networkInfo['up'] + networkInfo['down']):
                networkInfo = tmp

            # 取磁盘Io
            if os.path.exists('/proc/diskstats'):
                diskio_2 = psutil.disk_io_counters()
                if not diskio_1:
                    diskio_1 = diskio_2
                tmp = {}
                tmp['read_count'] = diskio_2.read_count - diskio_1.read_count
                tmp['write_count'] = diskio_2.write_count - diskio_1.write_count
                tmp['read_bytes'] = diskio_2.read_bytes - diskio_1.read_bytes
                tmp['write_bytes'] = diskio_2.write_bytes - diskio_1.write_bytes
                tmp['read_time'] = diskio_2.read_time - diskio_1.read_time
                tmp['write_time'] = diskio_2.write_time - diskio_1.write_time

                if not diskInfo:
                    diskInfo = tmp
                else:
                    diskInfo['read_count'] += tmp['read_count']
                    diskInfo['write_count'] += tmp['write_count']
                    diskInfo['read_bytes'] += tmp['read_bytes']
                    diskInfo['write_bytes'] += tmp['write_bytes']
                    diskInfo['read_time'] += tmp['read_time']
                    diskInfo['write_time'] += tmp['write_time']

                diskio_1 = diskio_2

            # print diskInfo

            if count >= 12:
                try:
                    addtime = int(time.time())
                    deltime = addtime - (day * 86400)

                    data = (cpuInfo['used'], cpuInfo['mem'], addtime)
                    sql.table('cpuio').add('pro,mem,addtime', data)
                    sql.table('cpuio').where("addtime<?", (deltime,)).delete()

                    data = (networkInfo['up'] / 5, networkInfo['down'] / 5, networkInfo['upTotal'], networkInfo[
                            'downTotal'], networkInfo['downPackets'], networkInfo['upPackets'], addtime)
                    sql.table('network').add(
                        'up,down,total_up,total_down,down_packets,up_packets,addtime', data)
                    sql.table('network').where(
                        "addtime<?", (deltime,)).delete()
                    if os.path.exists('/proc/diskstats'):
                        data = (diskInfo['read_count'], diskInfo['write_count'], diskInfo['read_bytes'], diskInfo[
                                'write_bytes'], diskInfo['read_time'], diskInfo['write_time'], addtime)
                        sql.table('diskio').add(
                            'read_count,write_count,read_bytes,write_bytes,read_time,write_time,addtime', data)
                        sql.table('diskio').where(
                            "addtime<?", (deltime,)).delete()

                    # LoadAverage
                    load_average = sm.GetLoadAverage(None)
                    lpro = round(
                        (load_average['one'] / load_average['max']) * 100, 2)
                    if lpro > 100:
                        lpro = 100
                    sql.table('load_average').add('pro,one,five,fifteen,addtime', (lpro, load_average[
                        'one'], load_average['five'], load_average['fifteen'], addtime))

                    lpro = None
                    load_average = None
                    cpuInfo = None
                    networkInfo = None
                    diskInfo = None
                    count = 0
                    reloadNum += 1
                    if reloadNum > 1440:
                        if os.path.exists('data/ssl.pl'):
                            os.system(
                                '/etc/init.d/bt restart > /dev/null 2>&1')
                        reloadNum = 0
                except Exception, ex:
                    print str(ex)
            del(tmp)

            time.sleep(5)
            count += 1
    except Exception, ex:
        print str(ex)
        time.sleep(30)
        systemTask()


def GetMemUsed():
    # 取内存使用率
    try:
        import psutil
        mem = psutil.virtual_memory()
        memInfo = {'memTotal': mem.total / 1024 / 1024, 'memFree': mem.free / 1024 / 1024,
                   'memBuffers': mem.buffers / 1024 / 1024, 'memCached': mem.cached / 1024 / 1024}
        tmp = memInfo['memTotal'] - memInfo['memFree'] - \
            memInfo['memBuffers'] - memInfo['memCached']
        tmp1 = memInfo['memTotal'] / 100
        return (tmp / tmp1)
    except:
        return 1

# 检查502错误


def check502():
    try:
        phpversions = ['53', '54', '55', '56', '70', '71', '72']
        for version in phpversions:
            if not os.path.exists('/etc/init.d/php-fpm-' + version):
                continue
            if checkPHPVersion(version):
                continue
            if startPHPVersion(version):
                public.WriteLog('PHP守护程序', '检测到PHP-' + version + '处理异常,已自动修复!')
    except:
        pass


def startPHPVersion(version):
    # 处理指定PHP版本
    try:
        fpm = '/etc/init.d/php-fpm-' + version
        if not os.path.exists(fpm):
            return False

        # 尝试重载服务
        os.system(fpm + ' reload')
        if checkPHPVersion(version):
            return True

        # 尝试重启服务
        cgi = '/tmp/php-cgi-' + version
        pid = '/www/server/php' + version + '/php-fpm.pid'
        os.system('pkill -9 php-fpm-' + version)
        time.sleep(0.5)
        if not os.path.exists(cgi):
            os.system('rm -f ' + cgi)
        if not os.path.exists(pid):
            os.system('rm -f ' + pid)
        os.system(fpm + ' start')
        if checkPHPVersion(version):
            return True

        # 检查是否正确启动
        if os.path.exists(cgi):
            return True
    except:
        return True


def checkPHPVersion(version):
    # 检查指定PHP版本
    try:
        url = 'http://127.0.0.1/phpfpm_' + version + '_status'
        result = public.httpGet(url)
        # 检查nginx
        if result.find('Bad Gateway') != -1:
            return False
        # 检查Apache
        if result.find('Service Unavailable') != -1:
            return False
        if result.find('Not Found') != -1:
            CheckPHPINFO()

        # 检查Web服务是否启动
        if result.find('Connection refused') != -1:
            global isTask
            if os.path.exists(isTask):
                isStatus = public.readFile(isTask)
                if isStatus == 'True':
                    return True
            filename = '/etc/init.d/nginx'
            if os.path.exists(filename):
                os.system(filename + ' start')
            filename = '/etc/init.d/httpd'
            if os.path.exists(filename):
                os.system(filename + ' start')

        return True
    except:
        return True


def CheckPHPINFO():
    # 检测PHPINFO配置
    php_versions = ['53', '54', '55', '56', '70', '71', '72']
    setupPath = '/www/server'
    path = setupPath + '/panel/vhost/nginx/phpinfo.conf'
    if not os.path.exists(path):
        opt = ""
        for version in php_versions:
            opt += "\n\tlocation /" + version + \
                " {\n\t\tinclude enable-php-" + version + ".conf;\n\t}"

        phpinfoBody = '''server
{
    listen 80;
    server_name 127.0.0.2;
    allow 127.0.0.1;
    index phpinfo.php index.html index.php;
    root  /www/server/phpinfo;
%s   
}''' % (opt,)
        public.writeFile(path, phpinfoBody)

    path = setupPath + '/panel/vhost/apache/phpinfo.conf'
    if not os.path.exists(path):
        opt = ""
        for version in php_versions:
            opt += """\n<Location /%s>
    SetHandler "proxy:unix:/tmp/php-cgi-%s.sock|fcgi://localhost"
</Location>""" % (version, version)

        phpinfoBody = '''
<VirtualHost *:80>
DocumentRoot "/www/server/phpinfo"
ServerAdmin phpinfo
ServerName 127.0.0.2
%s
<Directory "/www/server/phpinfo">
    SetOutputFilter DEFLATE
    Options FollowSymLinks
    AllowOverride All
    Order allow,deny
    Allow from all
    DirectoryIndex index.php index.html index.htm default.php default.html default.htm
</Directory>
</VirtualHost>
''' % (opt,)
        public.writeFile(path, phpinfoBody)

# 502错误检查线程


def check502Task():
    try:
        while True:
            if os.path.exists('/www/server/panel/data/502Task.pl'):
                check502()
            time.sleep(600)
    except:
        time.sleep(600)
        check502Task()

# 自动结束异常进程


def btkill():
    import btkill
    b = btkill.btkill()
    b.start()

if __name__ == "__main__":
    os.system('rm -rf /www/server/phpinfo/*')
    if os.path.exists('/www/server/nginx/sbin/nginx'):
        pfile = '/www/server/nginx/conf/enable-php-72.conf'
        if not os.path.exists(pfile):
            pconf = '''location ~ [^/]\.php(/|$)
{
    try_files $uri =404;
    fastcgi_pass  unix:/tmp/php-cgi-72.sock;
    fastcgi_index index.php;
    include fastcgi.conf;
    include pathinfo.conf;
}'''
            public.writeFile(pfile, pconf)
    import threading
    t = threading.Thread(target=systemTask)
    t.setDaemon(True)
    t.start()

    p = threading.Thread(target=check502Task)
    p.setDaemon(True)
    p.start()

    #p = threading.Thread(target=btkill)
    # p.setDaemon(True)
    # p.start()

    startTask()