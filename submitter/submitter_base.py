import os
from datetime import datetime

from Qt import QtCompat
from Qt import QtCore
from Qt.QtWidgets import QMainWindow
from Qt.QtWidgets import QMessageBox
from Qt.QtWidgets import QDesktopWidget

import config
from artfx_job import ArtFxJob, set_engine_client


class Submitter(QMainWindow):

    def __init__(self, parent=None):
        super(Submitter, self).__init__(parent)
        # setup ui
        QtCompat.loadUi(config.ui_path, self)
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)
        self.center()
        self.bt_render.clicked.connect(self.pre_submit)
        self.widget_frame.setVisible(False)
        self.rb_frame_range.clicked.connect(self.toggle)
        self.rb_frame.clicked.connect(self.toggle)
        self.input_frame_per_task.setValue(int(10))
        self.input_frame_increment.setText("1")
        self.input_frame_start.setText("1")
        self.input_frame_end.setText("2")
        self.current_project = self.get_project()
        # for project in config.projects:
        #     self.list_project.addItem(project["short_name"])
        #     if self.current_project == project:
        #         items = self.list_project.findItems(project["short_name"], QtCore.Qt.MatchCaseSensitive)
        #         if items[0]:
        #             self.list_project.setCurrentItem(items[0])
        for pool in config.pools:
            self.list_project.addItem(pool)
        # Set default to work
        items = self.list_project.findItems("work", QtCore.Qt.MatchCaseSensitive)
        if items[0]:
            self.list_project.setCurrentItem(items[0])
        for ram in config.rams:
            self.cb_ram.addItem(ram)
        self.isDev = True if os.getenv("DEV_PIPELINE") else False

    def get_path(self):
        return None

    def center(self):
        qRect = self.frameGeometry()
        centerPoint = QDesktopWidget().availableGeometry().center()
        qRect.moveCenter(centerPoint)
        self.move(qRect.topLeft())

    def toggle(self):
        if self.rb_frame_range.isChecked():
            self.widget_frame.setVisible(True)
        else:
            self.widget_frame.setVisible(False)
            self.input_frame_start.setText('1')
            self.input_frame_end.setText('2')

    def pre_submit(self):
        """
        Need to get data from dcc and call submit
        self.submit(path, start, end)
        """
        raise NotImplementedError()

    def is_linux(self):
        for project in self.list_project.selectedItems():
            if str(project.text()) == "rackLinux":
                return True
        return False

    def get_project(self, path=None):
        path = path or self.get_path()
        if not path:
            raise ValueError("You need to be in a pipeline scene")
        path = path.replace(os.sep, "/")
        root = os.environ["ROOT_PIPE"] if os.environ["ROOT_PIPE"] else "D:/SynologyDrive"
        if path.startswith('//'):
            project_name = path.split('/')[4].upper()
        else:
            path = path.replace(root + "/", "")
            project_name = path.split('/')[0].upper()
        return [_proj for _proj in config.projects if str(project_name) == _proj["name"]][0] or None

    def submit(self, path, start, end, engine, plugins=None):
        job_name = str(self.input_job_name.text())
        if not job_name:
            self.info("Job name is needed")
        increment = int(self.input_frame_increment.text())
        frames_per_task = int(self.input_frame_per_task.value())
        pools_selected = []
        ram_selected = self.cb_ram.currentText()
        path = path.replace(os.sep, "/")

        if int(frames_per_task) < 5:
            self.error("You need to use minimum 5 frame per task")

        # # # # # DIRMAP # # # #
        path = self.create_render_file(path)

        # # # # # WORKSPACE # # # # #
        if '/scenes' not in path:
            self.error('No workspace found (/scenes)')
        workspace = path.split('/scenes')[0]

        # # # # # POOLS # # # # #
        isLinux = self.is_linux()
        if len(self.list_project.selectedItems()) < 1:
            self.error("You need to select a pool")
        for project in self.list_project.selectedItems():
            # # Project
            # _name = [_proj["name"] for _proj in config.projects if str(project.text()) == _proj["short_name"]] or None
            # if _name:
            #     pools_selected.append("p_{0!s}".format(_name[0].lower()))
            #     continue
            # Linux Rack
            if str(project.text()) == "rackLinux":
                pools_selected = ["rackLinux"]
                break
            # Pool
            pools_selected.append(str(project.text()).lower())

        # # # # # FRAMES # # # # #
        if not self.rb_frame.isChecked():
            start = int(self.input_frame_start.text())
            end = int(self.input_frame_end.text())
        frames = str(start) + "-" + str(end)
        print("Render Frames : " + frames)

        # # # # # SERVICES # # # # #
        if len(pools_selected) == 1:
            services = pools_selected[0]
        else:
            services = "(" + " || ".join(pools_selected) + ")"
        if ram_selected == "ram_lower":
            services = services + " && !ram_32"
        elif ram_selected == "ram_32":
            services = services + " && ram_32"
        print("Render on : " + services)

        # # # # # ENGINE CLIENT # # # # #
        set_engine_client(user=("artfx" if isLinux else "admin"))

        # # # # # JOB # # # # #
        job = ArtFxJob(title=job_name, priority=100, service=services)

        try:
            if frames_per_task > (end - start):
                frames_per_task = (end - start + 1)
            for i in range(start, end + 1, frames_per_task):
                # # # # # BEFORE TASK # # # #
                pre_command = None
                if not isLinux:
                    pre_command = ["cmd", "/c", "//multifct/tools/renderfarm/misc/tractor_add_srv_key.bat"]
                # if engine == "houdini":  # TODO do the print env for all dcc
                #     pre_command = ["cmd", "/c", "C:/Houdini18/bin/hconfig.exe && //192.168.2.250/tools/renderfarm/misc/tractor_add_srv_key.bat"]
                # # # # # TASKS # # # # #
                task_end_frame = (i + frames_per_task - 1) if (i + frames_per_task - 1) < end else end
                task_command = self.task_command(isLinux, i, task_end_frame, path, workspace)
                task_name = "frame {start}-{end}".format(start=str(i), end=str(task_end_frame))
                # # # # # CLEAN UP # # # # #
                executables = config.batcher[engine]["cleanup"]["linux" if isLinux else "win"]
                if executables:
                    if type(executables) == str:
                        executables = [executables]
                job.add_task(task_name, task_command, services, path, self.current_project["server"], engine, plugins, executables, isLinux, pre_command)  #
            job.comment = str(self.current_project["name"])
            job.projects = [str(self.current_project["name"])]
            if self.isDev:
                print(job.asTcl())
            job.spool(owner=("artfx" if isLinux else str(self.current_project["name"])))
            self.success()
        except Exception as ex:
            self.error(ex.message)

    def task_command(self, is_linux, frame_start, frame_end, file_path, workspace=""):
        """
        Command for each task of the job (need to be change for each dcc)
        :param bool is_linux: Is linux ? (true = linux, false = win)
        :param int frame_start: Task start frame
        :param int frame_end: Task end frame
        :param str file_path: Path to the scene to render
        :param str workspace: Path to the workspace folder
        :return: The command in str or list
        :rtype: str or list
        """
        raise NotImplementedError()

    def success(self):
        """
        Success message box
        """
        msg = QMessageBox()
        msg.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)
        msg.setIcon(QMessageBox.Information)
        msg.setText("Job Send !")
        msg.setWindowTitle("RenderFarm")
        msg.setStandardButtons(QMessageBox.Ok)
        msg.buttonClicked.connect(self.close)
        msg.exec_()

    def error(self, message):
        """
        Error message box
        """
        msg = QMessageBox()
        msg.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)
        msg.setIcon(QMessageBox.Critical)
        msg.setText(message)
        msg.setWindowTitle("RenderFarm")
        msg.setStandardButtons(QMessageBox.Ok)
        msg.buttonClicked.connect(msg.close)
        msg.exec_()
        raise Exception(message)

    def info(self, message):
        """
        Error message box
        """
        msg = QMessageBox()
        msg.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)
        msg.setIcon(QMessageBox.Information)
        msg.setText(message)
        msg.setWindowTitle("RenderFarm")
        msg.setStandardButtons(QMessageBox.Ok)
        msg.buttonClicked.connect(self.close)
        msg.exec_()

    def create_render_file(self, path):
        """
        Create a tempory render scene file to avoid scene modification
        """
        proj = self.current_project or self.get_project(path)
        isLinux = self.is_linux()
        local_root = os.environ["ROOT_PIPE"] or "D:/SynologyDrive"
        local_project = '{}/{}'.format(local_root, proj["name"])
        template_server = '/{}/PFE_RN_2021/{}' if isLinux else '//{}/PFE_RN_2021/{}'
        server_project = template_server.format(proj["server"], proj["name"])

        # # # # TEMP FILE # # # #
        file_name = os.path.basename(path)
        file_split = file_name.split(".")
        path_split = path.split("/")
        render_path = '/'.join(path_split[:-2]) + '/render'
        # Submission on the server directly
        # Use windows path becose only windows use submitter
        server_project_win = '//{}/PFE_RN_2021/{}'.format(proj["server"], proj["name"])
        render_path = render_path.replace('D:/SynologyDrive/{}'.format(proj["name"]), server_project_win)
        now = datetime.now()
        timestamp = now.strftime("%m-%d-%Y_%H-%M-%S")
        new_name = "{version}_{file_name}_{timestamp}.{extension}".format(version=path_split[-2], file_name=file_split[0],
                                                                          timestamp=timestamp, extension=file_split[-1])
        new_name_path = os.path.join(render_path, new_name).replace(os.sep, '/')
        print("check if path exist : " + render_path)
        if not os.path.exists(render_path):
            if not os.path.exists(os.path.dirname(render_path)):
                os.makedirs(os.path.dirname(render_path))
            os.mkdir(render_path)

        # # # # DIRMAP # # # #
        self.set_dirmap(local_project, server_project, new_name_path, path)
        # Remap to local path for comand dirmap by tractor
        new_name_path = new_name_path.replace(server_project_win, 'D:/SynologyDrive/{}'.format(proj["name"]))
        return new_name_path

    def set_dirmap(self, local_project, server_project, new_name_path, path):
        pass


def run():
    win = Submitter()
    win.show()


if __name__ == '__main__':

    sub = Submitter()
    sub.show()
