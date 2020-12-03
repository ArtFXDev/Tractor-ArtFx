import os
import sys

import config

for path in config.tractor_lib_paths:
    sys.path.append(path)

import tractor.api.author as author


class ArtFxJob(author.Job):

    def __init__(self, *args, **kwargs):
        super(ArtFxJob, self).__init__(*args, **kwargs)
        self.dirmap_tractor()

    def add_task(self, name, command, services, executables=None, is_linux=True):
        """
        Add a task in the job
        :param str name: Name of the task
        :param str or list command: Command of the task
        :param str services: Services of the task
        :param array[str] executables: Executavle te clean up after task
        :param bool is_linux: If is linux
        """
        task = author.Task(title=name, argv=command, service=services)
        """
        # # # # # CLEAN UP # # # # #
        for executable in executables:
            if not is_linux:
                cmd = 'tasklist | find /i "Render.exe" && taskkill /im Render.exe /F || echo process Render.exe not running.'
                task.addCleanup(author.Command(argv=cmd, msg="Kill executable"))
            else:
                task.addCleanup(author.Command(argv="pkill -f {}".format(executable), msg="Kill executable"))             
        """
        self.addChild(task)


    def dirmap_tractor(self):
        """
        Tractor dirmap with config.project
        """
        local_root = os.environ["ROOT_PIPE"] or "D:/SynologyDrive"

        for project in config.projects:
            local_project = local_root + "/" + project["name"]
            srv_project_win = "//{server}/PFE_RN_2021/{name}".format(server=project["server"], name=project["name"])
            srv_project_linux = "/{server}/{name}".format(server=project["server"], name=project["name"])

            self.newDirMap(src=local_project, dst=srv_project_win, zone="UNC")
            self.newDirMap(src=local_project, dst=srv_project_linux, zone="NFS")


def set_engine_client(user):
    author.setEngineClientParam(user=user, debug=True)
