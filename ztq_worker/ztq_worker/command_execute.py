# -*- encoding: utf-8 -*-

#from zopen.transform import set_drive_config
from config_manager import safe_get_host, set_config
from job_thread_manager import JobThreadManager, kill_threads
from system_info import get_cpu_style, get_cpu_usage, get_mem_usage
import os
import sys
import traceback
import time
import ztq_core

# 管理工作线程, 添加线程、删除线程、保存信息
job_thread_manager = JobThreadManager()

def set_job_threads(config_dict):
    """ 根据配置信息和job_thread_manager.threads 的数量差来退出/增加线程
        剩下的修改queue_name, interval
    """
    tmp_jobs = job_thread_manager.threads.copy()
    config = []
    # 将config_dict转换格式为dicter = [{'queue':'q01', 'interval':6, }, ]
    for queue_name, values in config_dict.items():
        for value in values:
            dicter = dict( queue=queue_name )
            dicter.update(value)
            config.append(dicter)

    diff_job = len(config) - len(tmp_jobs)
    if diff_job > 0: # 需要增加线程
        for i in xrange(diff_job):
            conf = config.pop()
            job_thread_manager.add(conf['queue'], conf['interval'], conf.get('from_right', True))

    elif diff_job < 0: # 需要退出线程
        for key in tmp_jobs.keys():
            tmp_jobs.pop(key)
            job_thread_manager.stop(key)
            diff_job += 1
            if diff_job >= 0:
                break

    # 剩下的修改queue、interval、from_right, 如果有
    for index, job_thread in enumerate(tmp_jobs.values()):
        conf = config[index]
        job_thread.queue_name = conf['queue']
        job_thread.sleep_time = conf['interval']
        job_thread.from_right = conf.get('from_right', True)

def init_job_threads(config_dict):
    # 启动工作线程
    set_job_threads(config_dict)
    # 保存信息
    config = {}
    for queue_name, values in config_dict.items():
        sleeps = [str(x['interval']) for x in values]
        config[queue_name] = ','.join(sleeps)
    set_config(config, 'queues')

    # 将一些信息补全，让监视界面认为这个worker已经启动
    alias = safe_get_host('server', 'alias')
    # 初始化
    dispatcher_config = ztq_core.get_dispatcher_config()
    if not dispatcher_config: 
        dispatcher_config = {'queue_weight':{},'worker_weight':{}}
    # set dispatcher config
    worker_weight = dispatcher_config['worker_weight']
    if not worker_weight.get(alias, 0):
        worker_weight[alias] = 5 
        ztq_core.set_dispatcher_config(dispatcher_config)
    # set worker config
    worker_config = ztq_core.get_worker_config()
    worker_config[alias] = config_dict 

def set_dirve( from_mime, to_mime, conf):
    """ 根据驱动配置, 更改驱动参数 """
    #set_drive_config(from_mime, to_mime, conf)
    pass

def report(start_time):
    """ 转换器向服务器报告状态 """
    cpu_style = get_cpu_style()
    cpu_percent = get_cpu_usage() 
    mem_percent, mem_total = get_mem_usage()
    ip = safe_get_host('server', 'alias')

    traceback_dict = {}
    for thread_id, frame in sys._current_frames().items():
        traceback_dict[thread_id] = traceback.format_stack(frame)

    # 向服务器报告
    return dict( ip=ip,
            cpu_style=cpu_style, 
            cpu_percent=cpu_percent, 
            mem_total=mem_total, 
            mem_percent=mem_percent, 
            started=start_time, 
            timestamp=int(time.time()),
            traceback=traceback_dict,
            )

def kill_transform(pid, timestamp):
    """ 中止 转换 """
    kill(pid)

def cancel_transform(pid, timestamp):
    """ 取消 转换 """
    kill(pid)

if os.sys.platform != 'win':
    def kill(pid):
        """ kill process by pid for linux """
        # XXX 无法杀孙子进程
        kill_command = "kill -9 `ps --no-heading --ppid %s|awk '{print $1}'` %s" % (pid, pid)
        os.system(kill_command)
else:
    def kill(pid):
        """ kill process by pid for windows """
        kill_command = "taskkill /F /T /pid %s" % pid
        os.system(kill_command)


def clear_transform_thread(threads=None):
    """ clear job_threads """
    threads = threads or job_thread_manager.threads
    names = threads.keys()
    job_threads = threads.values()

    # 将进程的stop 标志 设置为True
    map(job_thread_manager.stop, names)

    # 如果这个线程没有工作，只是在阻塞等待任务，就发送一个空的任务
    # 让这个线程立刻结束
    for job_thread in job_threads:
        if job_thread.start_job_time == 0:
            queue_name = job_thread.queue_name
            queue = ztq_core.get_task_queue(queue_name)
            queue.push('')

    # 等待线程退出
    for job_thread in job_threads:
        sys.stdout.write('wait the %s stop...\n'%job_thread.getName())
        job_thread.join(30)

import atexit
atexit.register(clear_transform_thread) # 系统退出后清理工作线程

