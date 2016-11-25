#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""A Hydra app for running the  model..

Basics
~~~~~~

A Hydra app for running the  model
Basic usage::

       import__network.py [-h]

Options
~~~~~~~

====================== ====== ============ =======================================
Option                 Short  Parameter    Description
====================== ====== ============ =======================================
``--help``             ``-h``              Show help message and exit.
``--template-id''      ``-t'' TEMPLATE-ID  The ID of the  Template
``--project-id''       ``-p'' PROJECT-ID   The ID of the project you want to
                                           import the network into.
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
                               validate_plugin_xml,\
                               RequestError,\
                               temp_ids
import os, sys

from datetime import datetime
    
from prototype import simulation_setup

log = logging.getLogger(__name__)

global __location__
__location__ = os.path.split(sys.argv[0])[0]

class NetworkImporter(object):
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

        #Dictionaries, keyed on their name, where all the nodes, links & groups will go
        self.hydra_nodes = {}
        self.hydra_links = {}
        self.hydra_groups = {}
        self.hydra_group_members = {}

        #Generators of NEGATIVE IDS for the nodes & links. 
        #Negative IDS are used as temporary client-side IDS until the network
        #is saved, at which point the resources will be given permanent, positive IDS.
        self.node_ids  = temp_ids()
        self.link_ids  = temp_ids()
        self.group_ids = temp_ids() # A group is an institution.
    
        #A mapping from the name of a type to the type itself.
        self.type_name_map = {}

        self.num_steps = 3

    def fetch_project(self, project_id):
        """
            If a project ID is not specified, a new one
            must be created to hold the incoming network. 
            If an ID is specified, we must retrieve the project to make sure
            it exists. If it does not exist, then throw an error.

            Returns the project object so that the network can access it's ID.
        """
        if project_id is not None:
            try:
                project = self.connection.call('get_project', {'project_id':project_id})
                log.info('Loading existing project (ID=%s)' % project_id)
                return project
            except RequestError, e:
                log.exception(e)
                raise HydraPluginError("An error occurred retrieving project ID %s"%project_id)

        #Using 'datetime.now()' in the name guarantees a unique project name.
        new_project = dict(
            name = "Hobbes Project created at %s" % (datetime.now()),
            description = \
            "Default project created by the %s plug-in." % \
                (self.__class__.__name__),
        )

        saved_project = self.connection.call('add_project', {'project':new_project})
        
        return saved_project 


    def get_attributes(self, template_id):
        if template_id is not None:
            #TODO replace this with get_all_template_attributes when the function
            #is available (not sure why it's not)
            attributes = self.connection.call('get_all_attributes', {})
        else:
            attributes = self.connection.call('get_all_attributes', {})
        
        attr_id_map = {}
        for a in attributes:
            attr_id_map[a.id] = a
        self.attr_id_map = attr_id_map

    def get_template(self, template_id):
        if template_id is not None:
            template = self.connection.call('get_template', {'template_id':int(template_id)})
        else:
            raise HydraPluginError("No template specified!")
        
        for t_type in template.types:
            self.type_name_map[t_type.name] = t_type

    def get__network(self):

        # create list of simulations with timestep information based upon information input
        # to models_input.xlsx (sheet: simulation)
        simulations = simulation_setup.create_simulations()  # list of simulation objects

        # for each simulation, load the network from models_input.xlsx (sheet: network)
        simulation_setup.load_network(simulations)

        # load institutions for each simulation
        simulation_setup.load_institutions(simulations)


        self._network = simulations[0].network

    def import_network(self, template_id, project_id):
        write_output("Writing network to file")
        write_progress(3, self.num_steps)

        for j_node in self._network.nodes:
            
            log.info("Node: %s", j_node.component_type)
            node_type = self.type_name_map.get(j_node.component_type)

            y = j_node.y
            if y > 800000:
                y = y - 1000000
            elif y > 400000:
                y = y - 400000

            node = dict(
                id = self.node_ids.next(),
                name = j_node.name,
                description = " Node",
                x    = str(j_node.x),
                y    = str(y),
                attributes = [],
                types = [{'template_id':int(template_id), 'id':int(node_type.id)}]
            )
            self.hydra_nodes[j_node.name] = node

        for j_link in self._network.links:
            link_type = self.type_name_map.get(j_link.component_type)
            log.info("Link: %s", j_link.component_type)
            link = dict(
                id = self.link_ids.next(),
                name = j_link.name,
                description = " Link",
                node_1_id = self.hydra_nodes[j_link.start_node.name]['id'],
                node_2_id = self.hydra_nodes[j_link.end_node.name]['id'],
                attributes = [],
                types = [{'template_id':int(template_id), 'id':link_type.id}]
            )
            self.hydra_links[j_link.name] = link


        for j_inst in self._network.institutions:
            group_type = self.type_name_map.get(j_inst.component_type)
            log.info("Group: %s", j_inst.component_type)
            group = dict(
                id = self.group_ids.next(),
                name = j_inst.name,
                description = "A  Model Institution",
                attributes = [],
                types = [{'template_id':int(template_id), 'id':group_type.id}]
            )
            self.hydra_groups[j_inst.name] = group

        project = self.fetch_project(project_id)
        project_id = project.id

        network_type = self.type_name_map.get('Network')

        hydra_network = {
            'name' : " Network (%s)"%datetime.now(),
            'description' : " Network, imported directly from the prototype",
            'nodes': self.hydra_nodes.values(),
            'links': self.hydra_links.values(),
            'project_id' : project_id,
            'projection':'EPSG:2229',
            'resourcegroups': self.hydra_groups.values(),
            'scenarios': [],
            'types' : [{'template_id':int(template_id), 'id':network_type.id}],
        }

        self.network = self.connection.call('add_network', {'net':hydra_network})
        return self.network


    def import_scenario(self):
        
        for n in self.network.nodes:
            self.hydra_nodes[n.name] = n
        for l in self.network.links:
            self.hydra_links[l.name] = l
        for g in self.network.resourcegroups:
            self.hydra_groups[g.name] = g

        hydra_group_members = []
        for j_inst in self._network.institutions:
            group_id = self.hydra_groups[j_inst.name].id

            for n in j_inst.nodes:
                hydra_group_members.append(
                {
                    'ref_key':'NODE',
                    'ref_id' : self.hydra_nodes[n.name]['id'],
                    'group_id' : group_id, 
                }
                )

            for l in j_inst.links:
                hydra_group_members.append(
                {
                    'ref_key':'LINK',
                    'ref_id' : self.hydra_links[l.name]['id'],
                    'group_id' : group_id, 
                }
                )
            for i in j_inst.institutions:
                hydra_group_members.append(
                {
                    'ref_key':'GROUP',
                    'ref_id' : self.hydra_groups[i.name]['id'],
                    'group_id' : group_id, 
                }
                )

        scenario = dict(
            name = "Baseline",
            description = "Scenario imported from the import app",
            network_id = self.network.id,
            resourcegroupitems = hydra_group_members,
            resourcescenarios  = []
        )

        write_output("Finished Writing Output.")

        self.scenario = self.connection.call('add_scenario', {
            'network_id': self.network.id,
            'scen':scenario})

        return self.scenario


def commandline_parser():
    parser = ap.ArgumentParser(
        description="""Run the  prototype from Hydra
                    Written by Stephen Knox <stephen.knox@manchester.ac.uk>
                    (c) Copyright 2015, University of Manchester.
        """, epilog="For more information visit www.hydraplatform.org")
    parser.add_argument('-t', '--template-id',
                        help='''The ID of the  Template''')
    parser.add_argument('-p', '--project-id',
                        help='''The ID of the target project''')
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
    network_importer = NetworkImporter(url=args.server_url, session_id=args.session_id)
    errors = []
    network_id = None
    scenario_id = None
    try:
        write_output("Starting App")
        write_progress(1, network_importer.num_steps) 

        validate_plugin_xml(os.path.join(__location__, 'plugin.xml'))
        
        network_importer.get__network()
        
        network_importer.get_template(args.template_id)

        network = network_importer.import_network(args.template_id, args.project_id)
        network_id = network.id

        scenario = network_importer.import_scenario()
        scenario_id = scenario.id

        message = "Import Complete"
    except HydraPluginError as e:
        message="An error has occurred"
        errors = [e.message]
        log.exception(e)
    except Exception, e:
        message="An error has occurred"
        log.exception(e)
        errors = [e]

    xml_response = create_xml_response('Import  Network',
                                                 network_id,
                                                 [scenario_id],
                                                 errors,
                                                 [],
                                                 message,
                                                 network_importer.files)
    print xml_response
