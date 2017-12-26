# -*- coding: utf-8 -*-
# Fielname = sim.py

"""
SIM class.
Created on 2017-12-19
@author: dongxiaoguang
"""

import math
import numpy as np
from pathgen import pathgen
import matplotlib.pyplot as plt

D2R = math.pi/180
# built-in mobility
high_mobility = np.array([1.0, 0.5, 2.0])

class Sim(object):
    '''
    Simulation class.
    '''
    def __init__(self, fs, imu, path, mode='flight', env='2g_random', algorithm=None):
        '''
        Args:
            fs: [fs_imu, fs_gps, fs_mag], Hz
            imu:
            mode: simu mode could be a string to specify a built-in mode:
                    'flight':
                or a numpy array of size (3,) to customize the sim mode.
            path: a .csv file to define the waypoints
                row 1: initial states.
                    3 initial position (LLA, deg, meter),
                    3 initial velocity in body frame(m/s),
                    3 initial attitude (Euler angles, deg)
                row >=2: motion commands.
                    col 1: motion type.
                        1: Euler angles change rate and body frame velocity change rate.
                        2: absolute att and absolute vel to rech.
                        3: relative att and vel change.
                        4: absolute att, relative vel.
                        5: relative att, absolute vel.
                    col 2-7: motion command (deg, m/s).
                        [yaw, pitch, roll, vx (velocity along body x axis), reserved, reserved].
                    col 8: maximum time for the given segment, sec.
                    col 9: reserved.
            env:
            algorithm:
        '''
        ########## configure simulation ##########
        self.sim_complete = False   # simulation complete successfully
        self.sim_count = 1          # simulation count
        self.imu = imu              # imu config
        ########## possible data generated by simulation ##########
        self.fs = Sim_data(name='fs', description='sample frequency of imu',\
                           plottable=False)
        self.fs.data = fs[0]
        self.ref_frame = Sim_data(name='ref_frame', description='reference frame',\
                                  plottable=False)
        self.ref_frame.data = 0 # NED
        # reference data
        self.time = Sim_data(name='time', description='sample time, start from 1')
        self.gps_time = Sim_data(name='gps_time', description='GPS sample time')
        self.ref_pos = Sim_data(name='ref_pos', description='true pos',\
                                legend=['ref_pos_x', 'ref_pos_y', 'ref_pos_z'])
        self.ref_vel = Sim_data(name='ref_vel', description='true vel',\
                                legend=['ref_vel_x', 'ref_vel_y', 'ref_vel_z'])
        self.ref_att = Sim_data(name='ref_att', description='true attitude (Euler angles, ZYX)',\
                                legend=['ref_Yaw', 'ref_Pitch', 'ref_Roll'])
        self.ref_gyro = Sim_data(name='ref_gyro', description='true angular velocity',\
                                 legend=['ref_gyro_x', 'ref_gyro_y', 'ref_gyro_z'])
        self.ref_accel = Sim_data(name='ref_accel', description='true accel',\
                                  legend=['ref_accel_x', 'ref_accel_y', 'ref_accel_z'])
        self.ref_gps = Sim_data(name='ref_gps', description='true GPS pos/vel',\
                                legend=['ref_gps_x', 'ref_gps_y', 'ref_gps_z',\
                                        'ref_gps_vx', 'ref_gps_vy', 'ref_gps_vz'])
                                # downsampled true pos/vel, first row is sample index,
                                # sync with self.time
        self.ref_mag = Sim_data(name='ref_mag', description='true magnetic field',\
                                legend=['ref_mag_x', 'ref_mag_y', 'ref_mag_z'])
        # simulation results
        self.pos = Sim_data(name='pos', description='sim pos',\
                            legend=['pos_x', 'pos_y', 'pos_z'])
        self.vel = Sim_data(name='vel', description='sim vel',\
                            legend=['vel_x', 'vel_y', 'vel_z'])
        self.att_quat = Sim_data(name='att_quat', description='sim att (quaternion)',\
                                 legend=['q0', 'q1', 'q2', 'q3'])
        self.att_euler = Sim_data(name='att_euler', description='sim att (Euler angles, ZYX)',\
                                  legend=['Yaw', 'Pitch', 'Roll'])
        self.gyro = Sim_data(name='gyro', description='gyro measurements',\
                             legend=['gyro_x', 'gyro_y', 'gyro_z'])
        self.accel = Sim_data(name='accel', description='accel measurements',\
                              legend=['accel_x', 'accel_y', 'accel_z'])
        self.gps = Sim_data(name='gps', description='GPS measurements',\
                            legend=['gps_x', 'gps_y', 'gps_z', 'gps_vx', 'gps_vy', 'gps_vz'])
        self.mag = Sim_data(name='mag', description='magnetometer measurements',\
                            legend=['mag_x', 'mag_y', 'mag_z'])
        self.wb = Sim_data(name='wb', description='gyro bias estimation',\
                           legend=['gyro_bias_x', 'gyro_bias_y', 'gyro_bias_z'])
        self.ab = Sim_data(name='ab', description='accel bias estimation',\
                           legend=['accel_bias_x', 'accel_bias_y', 'accel_bias_z'])
        self.av_t = Sim_data(name='av_t', description='Allan var time')
        self.av_gyro = Sim_data(name='av_gyro', description='Allan var of gyro',\
                                logx=True, logy=True,\
                                legend=['av_wx', 'av_wy', 'av_wz'],\
                                pre_func=np.sqrt)
        self.av_accel = Sim_data(name='av_accel', description='Allan var of accel',\
                                 logx=True, logy=True,\
                                 legend=['av_ax', 'av_ay', 'av_az'],\
                                 pre_func=np.sqrt)

        ########## supported data ##########
        '''
        each item in the supported data should be either scalar or numpy.array of size(n, dim).
        n is the sample number, dim is a set of data at time tn. For example, accel is nx3,
        att_quat is nx4, av_t is (n,)
        '''
        # data that can be used as input to the algorithm
        '''
        There are two kinds of data that can be used as algorithm input: constant that stays the
        same for all simulations, varying that varies for different simulations.
        For example, fs stay the same for all simulations, reference data stay the same for all
        simulations, and sensor data vary for different simulations.
        '''
        self.supported_in_constant = {
            self.fs.name: self.fs.description,
            self.ref_frame.name: self.ref_frame.description,
            self.ref_pos.name: self.ref_pos.description,
            self.ref_vel.name: self.ref_vel.description,
            self.ref_att.name: self.ref_att.description,
            self.ref_gyro.name: self.ref_gyro.description,
            self.ref_accel.name: self.ref_accel.description}
        self.supported_in_varying = {
            self.gyro.name: self.gyro.description,
            self.accel.name: self.accel.description}
        if self.imu.gps:    # optional GPS
            self.supported_in_constant[self.ref_gps.name] = self.ref_gps.description
            self.supported_in_constant[self.gps_time] = self.gps_time.description
            self.supported_in_varying[self.gps.name] = self.gps.description
        if self.imu.magnetometer:   # optional mag
            self.supported_in_constant[self.ref_mag.name] = self.ref_mag.description
            self.supported_in_varying[self.mag.name] = self.mag.description
        # algorithm output that can be handled by Sim class
        # algorithm outputs vary for different simulations
        self.supported_out = {
            self.pos.name: self.pos.description,
            self.vel.name: self.vel.description,
            self.att_quat.name: self.att_quat.description,
            self.att_euler.name: self.att_euler.description,
            self.wb.name: self.wb.description,
            self.ab.name: self.ab.description,
            self.av_t.name: self.av_t.description,
            self.av_gyro.name: self.av_gyro.description,
            self.av_accel.name: self.av_accel.description}
        # all available data
        self.res = {}
        # all available data for plot
        self.supported_plot = {}

        # read motion definition
        waypoints = np.genfromtxt(path, delimiter=',')
        if waypoints.shape[0] < 2 or waypoints.shape[1] != 9:
            raise ValueError('motion definition file must have nine columns \
                              and at least two rows and ')
        self.ini_pos_n = waypoints[0, 0:3]
        self.ini_pos_n[0] = self.ini_pos_n[0] * D2R
        self.ini_pos_n[1] = self.ini_pos_n[1] * D2R
        self.ini_vel_b = waypoints[0, 3:6]
        self.ini_att = waypoints[0, 6:9]
        self.motion_def = waypoints[1:, [0, 1, 2, 3, 4, 7]]
        self.motion_def[:, 1:4] = self.motion_def[:, 1:4] * D2R

        # generate GPS or not
        # output definitions
        self.output_def = np.array([[1.0, self.fs.data], [1.0, self.fs.data]])
        if self.imu.gps:
            self.output_def[1, 0] = 1.0
            self.output_def[1, 1] = fs[1]
        else:
            self.output_def[1, 0] = -1.0

        # flight mode
        if isinstance(mode, str):               # specify built-in mode
            self.mobility = high_mobility
        elif isinstance(mode, np.ndarray):      # customize the sim mode
            self.mobility = mode                # maneuver capability
        else:
            raise TypeError('mode should be a string or a numpy array of size (3,)')

        # environment-->vibraition params
        if isinstance(env, str):                # specify simple vib model
            pass
        elif isinstance(env, np.ndarray):       # customize the vib model with PSD
            pass
        else:
            raise TypeError('env should be a string or a numpy array of size (n,2)')
        self.vib_def = None

        # check algorithm
        self.algo = algorithm
        self.algo_in_expr = '['          # expression to generate input to the algorithm
        self.algo_out_expr = '['         # expression to handle algorithm output
        if algorithm is not None:
            try:
                n_in = len(algorithm.input)
                n_out = len(algorithm.output)
                # algorithm must have at least one input and one output
                if n_in < 1 or n_out < 1:
                    raise ValueError
                # prepare algorithm input and output
                if not self.parse_algo_in_out():
                    raise ValueError
            except ValueError:
                raise ValueError('check input and output definitions of the algorithm.')
            except:
                raise TypeError('algorithm is not valid.')

    def run(self, num_times=1):
        '''
        run simulation.
        Args:
            num_times: run the simulation for num_times times with given IMU error model.
        '''
        self.sim_count = int(num_times)
        if self.sim_count < 1:
            self.sim_count = 1
        ########## generate reference data ##########
        rtn = pathgen.path_gen(np.hstack((self.ini_pos_n, self.ini_vel_b, self.ini_att)),
                               self.motion_def, self.output_def, self.mobility,
                               self.ref_frame.data, self.imu.magnetometer)
        # save reference data
        self.time.data = rtn['nav'][:, 0]
        self.ref_pos.data = rtn['nav'][:, 1:4]
        self.ref_vel.data = rtn['nav'][:, 4:7]
        self.ref_att.data = rtn['nav'][:, 7:10]
        self.ref_accel.data = rtn['imu'][:, 1:4]
        self.ref_gyro.data = rtn['imu'][:, 4:7]
        if self.imu.gps:
            self.gps_time.data = rtn['gps'][:, 0]
            self.ref_gps.data = rtn['gps'][:, 1:7]
        if self.imu.magnetometer:
            self.ref_mag.data = rtn['mag'][:, 1:4]
        ########## simulation ##########
        for i in range(0, self.sim_count):
            i_str = str(i)
            # generate sensor data
            self.accel.data[i] = pathgen.acc_gen(self.fs.data, self.ref_accel.data,
                                                 self.imu.accel_err, self.vib_def)
            # np.savetxt(i_str+'_accel.txt', self.accel[i])
            self.gyro.data[i] = pathgen.gyro_gen(self.fs.data, self.ref_gyro.data,\
                                                 self.imu.gyro_err)
            # np.savetxt(i_str+'_gyro.txt', self.gyro[i])
            if self.imu.gps:
                self.gps.data[i] = pathgen.gps_gen(self.ref_gps.data, self.imu.gps_err,\
                                                   self.ref_frame.data)
                # np.savetxt(i_str+'_gps.txt', self.gps[i])
            if self.imu.magnetometer:
                self.mag.data[i] = pathgen.mag_gen(self.ref_mag.data, self.imu.mag_err)
                # np.savetxt(i_str+'_mag.txt', self.mag[i])
            # run specified algorithm
            if self.algo is not None:
                self.algo.run(eval(self.algo_in_expr.replace('NO_OF_SIM', i_str)))
                exec(self.algo_out_expr.replace('NO_OF_SIM', i_str) + ' = self.algo.get_results()')
        # simulation complete successfully
        self.sim_complete = True

    def results(self):
        '''
        simulation results.
        Returns: a dict contains all simulation results.
            ''
            ''
        '''
        if self.sim_complete:
            # data from pathgen are available after simulation
            self.res = self.supported_in_constant.copy()
            self.res.update(self.supported_in_varying)
            # add user specified algorithm output to results
            if self.algo is not None:
                for i in self.algo.output:
                    self.res[i] = self.supported_out[i]
            # generate supported plot
            self.supported_plot = self.res.copy()
            self.supported_plot.pop('fs')
            self.supported_plot.pop('ref_frame')
            # print(self.res)
            # print(self.supported_plot)
        return self.res

    def plot(self, what_to_plot, sim_idx=None):
        '''
        Plot specified results.
        Args:
            what_to_plot: a string list to specify what to plot. See manual for details.
            sim_idx: specify the simulation index. This can be an integer, or a list or tuple.
                Each element should be within [0, num_times-1]. Default is None, and plot data
                of all simulations.
        '''
        # check sim_idx
        if sim_idx is None:                 # no index specified, plot all data
            sim_idx = list(range(self.sim_count))
        elif isinstance(sim_idx, int):      # scalar input, convert to list
            sim_idx = [sim_idx]
        elif isinstance(sim_idx, float):
            sim_idx = [int(sim_idx)]
        invalid_idx = []
        for i in range(0, len(sim_idx)):    # a list specified, remove invalid values
            sim_idx[i] = int(sim_idx[i])
            if sim_idx[i] >= self.sim_count or sim_idx[i] < 0:
                invalid_idx.append(sim_idx[i])
                print('sim_idx[%s] = %s exceeds max simulation count: %s.'%\
                      (i, sim_idx[i], self.sim_count))
        for i in invalid_idx:
            sim_idx.remove(i)
        # dict of data to plot
        for i in what_to_plot:
            # print("data to plot: %s"% i)
            x_axis = self.time.data
            if i in self.supported_plot:
                if i in self.supported_in_constant:
                    if i == self.ref_gps.name or i == self.gps_time.name:
                        x_axis = self.gps_time.data
                    exec('self.' + i + '.plot(x_axis)')
                else:
                    if i == self.av_gyro.name or i == self.av_accel.name or i == self.av_t.name:
                        x_axis = self.av_t.data[0]
                    elif i == self.gps.name:
                        x_axis = self.gps_time.data
                    exec('self.' + i + '.plot(x_axis, sim_idx)')
            else:
                print('Unsupported plot: %s.'% i)
                # print("Only the following data are available for plot:")
                # print(list(self.supported_plot.keys()))
                # raise ValueError("Unsupported data to plot: %s."%data)
        # show figures
        plt.show()

    def summary(self):
        '''
        Summary of sim results.
        '''
        pass

    def parse_algo_in_out(self):
        '''
        Generate expressions to handle algorithm input and output.
        Args:
            algorithm: user specified algorithm class
        Returns:
            True if sueccess, False if error.
        '''
        for i in self.algo.input:
            if i in self.supported_in_constant:
                self.algo_in_expr += 'self.' + i + '.data'
                self.algo_in_expr += ', '
            elif i in self.supported_in_varying:
                self.algo_in_expr += 'self.' + i + '.data[NO_OF_SIM]'
                self.algo_in_expr += ', '
            else:
                return False
        for i in self.algo.output:
            if i in self.supported_out:
                self.algo_out_expr += 'self.' + i + '.data[NO_OF_SIM]'
                self.algo_out_expr += ', '
            else:
                return False
        self.algo_in_expr += ']'
        self.algo_out_expr += ']'
        return True

class Sim_data(object):
    '''
    Simulation data
    '''
    def __init__(self, name, description, plottable=True,\
                 logx=False, logy=False,\
                 grid='on', legend=None, pre_func=None):
        '''
        Set up data properties and plot properties.
        Args:
            name: string name of the data
            description: string description of the data
            logx: plot this data with log scaling on x axis
            logy: plot this data with log scaling on y axis
            grid: if this is not 'off', it will be changed to 'on'
            legend: tuple or list of strings of length dim.
        '''
        self.name = name
        self.description = description
        self.plottable = plottable
        self.logx = logx
        self.logy = logy
        self.grid = 'on'
        if grid.lower() == 'off':
            self.grid = grid
        self.legend = legend
        self.pre_func = pre_func
        self.data = {}  # a dict to store data

    def plot(self, x, key=None):
        '''
        Plot self.data[key]
        Args:
            key is a tuple or list of keys
            x: x axis data
        '''
        if self.plottable:
            if isinstance(self.data, dict):
                self.plot_dict(x, key)
            else:
                self.plot_array(x)

    def plot_dict(self, x, key):
        '''
        self.data is a dict. plot self.data according to key
        '''
        for i in key:
            if self.pre_func is not None:
                y = self.pre_func(self.data[i])
            else:
                y = self.data[i]
            plot_in_one_figure(x, y,\
                               logx=self.logx, logy=self.logy,\
                               title=self.name + '_' + str(i),\
                               grid=self.grid,\
                               legend=self.legend)

    def plot_array(self, x):
        '''
        self.data is a numpy.array
        '''
        plot_in_one_figure(x, self.data,\
                           logx=self.logx, logy=self.logy,\
                           title=self.name,\
                           grid=self.grid,\
                           legend=self.legend)

def plot_in_one_figure(x, y, logx=False, logy=False,\
                       title='Figure', grid='on', legend=None):
    '''
    Create a figure and plot x/y in this figure.
    Args:
        x: x axis data, np.array of size (n,) or (n,1)
        y: y axis data, np.array of size (n,dim)
        title: figure title
        gird: if this is not 'off', it will be changed to 'on'
        legend: tuple or list of strings of length dim.
    '''
    # create figure and axis
    fig = plt.figure(title)
    axis = fig.add_subplot(111)
    lines = []
    try:
        dim = y.ndim
        if dim == 1:
            if logx and logy:   # loglog
                line, = axis.loglog(x, y)
            elif logx:          # semilogx
                line, = axis.semilogx(x, y)
            elif logy:          # semilogy
                line, = axis.semilogy(x, y)
            else:               # plot
                line, = axis.plot(x, y)
            lines.append(line)
        elif dim == 2:
            for i in range(0, y.shape[1]):
                if logx and logy:   # loglog
                    line, = axis.loglog(x, y[:, i])
                elif logx:          # semilogx
                    line, = axis.semilogx(x, y[:, i])
                elif logy:          # semilogy
                    line, = axis.semilogy(x, y[:, i])
                else:               # plot
                    line, = axis.plot(x, y[:, i])
                lines.append(line)
        else:
            raise ValueError
    except:
        print(x.shape)
        print(y.shape)
        raise ValueError('Check input data y.')
    # legend
    if legend is not None:
        plt.legend(lines, legend)
    # grid
    if grid.lower() != 'off':
        plt.grid()
