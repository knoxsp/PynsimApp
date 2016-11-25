#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""A Hydra app for running the jordan model..

Basics
~~~~~~

A Hydra app for running the jordan model
Basic usage::

       run_jordan_prototype.py [-h] [-n network_id] [-s scenario_id] [-u] [-c] 

Options
~~~~~~~

====================== ====== ============ =======================================
Option                 Short  Parameter    Description
====================== ====== ============ =======================================
``--help``             ``-h``              Show help message and exit.
``--network-id         ``-n`` NETWORK_ID   The ID of the network to be exported.
``--scenario-id        ``-s`` SCENARIO_ID  The ID of the scenario to be exported.
                                           (optional)
``--server-url``       ``-u`` SERVER-URL   Url of the server the plugin will
                                           connect to.
                                           Defaults to localhost.
``--session-id``       ``-c`` SESSION-ID   Session ID used by the calling software.
                                           If left empty, the plugin will attempt
                                           to log in itself.
====================== ====== ============ =======================================

"""


import argparse as ap
import logging

from HydraLib.HydraException import HydraPluginError
from HydraLib.PluginLib import JsonConnection,\
                               create_xml_response,\
                               write_progress,\
                               write_output,\
                               validate_plugin_xml
import json
import os, sys


from HydraLib.xml2json import json2xml

log = logging.getLogger(__name__)

global __location__
__location__ = os.path.split(sys.argv[0])[0]

class ModelRunner(object):
    """
       Exporter of Hydra networks to JSON or XML files.
    """

    def __init__(self, url=None, session_id=None):

        #Record the names of the files created by the plugin so we can
        #display them to the user.
        self.files    = []

        #A mapping from attr ID to attr object. Makes searching for attributes
        #easier 
        self.attr_id_map = {}

        self.connection = JsonConnection(url)
        write_output("Connecting...")
        if session_id is not None:
            write_output("Using existing session %s"% session_id)
            self.connection.session_id=session_id
        else:
            self.connection.login()
        
        self.network = None

        self.num_steps = 3

    def get_attributes(self, template_id):
        if template_id is not None:
            #TODO: Find out why get_all_template_attributes isnt here.
            attributes = self.connection.call('get_all_attributes', 
                                            {'template_id':template_id})
        else:
            attributes = self.connection.call('get_all_attributes', {})
        
        attr_id_map = {}
        for a in attributes:
            attr_id_map[a.id] = a
        self.attr_id_map = attr_id_map

    def get_network_data(self, network_id, scenario_id):
        """
            Retrieve the network, identify the parameters to set, 
            set them and run the model. Then identify the results
            and set them back on the network.
        """

        write_output("Retrieving Network") 
        write_progress(2, self.num_steps) 
        if network_id is not None:

            if scenario_id is None:
                raise HydraPluginError("A scenario ID must be specified.")

            #The network ID can be specified to get the network...
            try:
                network_id = int(network_id)
                network = self.connection.call('get_network', {'network_id':network_id,
                                                        'scenario_ids':[int(scenario_id)]})

                write_output("Network retrieved")
            except Exception, e:
                log.exception(e)
                raise HydraPluginError("Network %s not found."%network_id)

        else:
            raise HydraPluginError("A network ID must be specified!")
        
        template_id = None
        if network.types is not None:
            template_id = network.types[0].template_id

        self.get_attributes(template_id)
       
        #if network.attributes is not None:
        #    raise HydraPluginError("There's no network attributes. Unable to run Model.")

        for net_ra in network.attributes:
             net_attr = self.attr_id_map[net_ra.attr_id]
        else:
            pass
            #raise HydraPluginError("There's no network attributes. Unable to run Model.")
        
        self.network = network


    def run_model(self):

        from jordanprototype import simulation_setup

        # create list of simulations with timestep information based upon information input
        # to models_input.xlsx (sheet: simulation)
        simulations = simulation_setup.create_simulations()  # list of simulation objects

        # for each simulation, load the network from models_input.xlsx (sheet: network)
        simulation_setup.load_network(simulations)

        # load institutions for each simulation
        simulation_setup.load_institutions(simulations)

        # load exogenous inputs for each simulation
        simulation_setup.load_exogenous_inputs(simulations)

        old_tariff = simulations[0].network.exogenous_inputs.amman_model_user_input_params[0]

        new_tariff = 2

        log.critical("Setting piped water tarriff factor from %s to %s", old_tariff, new_tariff)

        simulations[0].network.exogenous_inputs.amman_model_user_input_params[0] = new_tariff

        # load observations (simulation independent)
        simulation_setup.load_observations(simulations)

        # load engines for each simulation
        simulation_setup.load_engines(simulations)

        # run each simulation in simulations list
        for s in simulations:
            s.start()

        os.chdir(__location__)

    def write_network(self, network, target_dir):
        write_output("Writing network to file")
        write_progress(3, self.num_steps) 

        if self.as_xml is False:
            file_name = "network_%s.json"%(network['name'])
            self.files.append(os.path.join(target_dir, file_name))

            network_file = open(os.path.join(target_dir, file_name), 'w')
            network_file.write(json.dumps(network, sort_keys=True, indent=4, separators=(',', ': ')))
        else:
            file_name = "network_%s.xml"%(network['name'])
            self.files.append(os.path.join(target_dir, file_name))

            network_file = open(os.path.join(target_dir, file_name), 'w')
            json_network = {'network': network}
            network_file.write(json2xml(json_network))

        write_output("Network Written to %s "%(target_dir))

def commandline_parser():
    parser = ap.ArgumentParser(
        description="""Run the jordan prototype from Hydra
                    Written by Stephen Knox <stephen.knox@manchester.ac.uk>
                    (c) Copyright 2015, University of Manchester.
        """, epilog="For more information visit www.hydraplatform.org")
    parser.add_argument('-n', '--network-id',
                        help='''Specify the network_id of the network to be run.''')
    parser.add_argument('-s', '--scenario-id',
                        help='''Specify the ID of the scenario to be run. ''')
    parser.add_argument('-m', '--model-dir',
                        help='''Target directory''')
    parser.add_argument('-u', '--server-url',
                        help='''Specify the URL of the server to which this
                        plug-in connects.''')
    parser.add_argument('-c', '--session-id',
                        help='''Session ID. If this does not exist, a login will be
                        attempted based on details in config.''')
    return parser


if __name__ == '__main__':
    parser = commandline_parser()
    args = parser.parse_args()
    jp_runner = ModelRunner(url=args.server_url, session_id=args.session_id)
    errors = []
    try:
        write_output("Starting App")
        write_progress(1, jp_runner.num_steps) 

        validate_plugin_xml(os.path.join(__location__, 'plugin.xml'))
        
        jp_runner.get_network_data(args.network_id, args.scenario_id)
        jp_runner.run_model()
        message = "Model Run Complete"
    except HydraPluginError as e:
        message="An error has occurred"
        errors = [e.message]
        log.exception(e)
    except Exception, e:
        message="An error has occurred"
        log.exception(e)
        errors = [e]

    xml_response = create_xml_response('Run Jordan Model',
                                                 args.network_id,
                                                 [],
                                                 errors,
                                                 [],
                                                 message,
                                                 jp_runner.files)
    print xml_response
