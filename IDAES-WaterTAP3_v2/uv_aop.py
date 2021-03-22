#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Feb  5 13:26:35 2021

@author: ksitterl
"""

##############################################################################
# Institute for the Design of Advanced Energy Systems Process Systems
# Engineering Framework (IDAES PSE Framework) Copyright (c) 2018-2020, by the
# software owners: The Regents of the University of California, through
# Lawrence Berkeley National Laboratory,  National Technology & Engineering
# Solutions of Sandia, LLC, Carnegie Mellon University, West Virginia
# University Research Corporation, et al. All rights reserved.
#
# Please see the files COPYRIGHT.txt and LICENSE.txt for full copyright and
# license information, respectively. Both files are also available online
# at the URL "https://github.com/IDAES/idaes-pse".
##############################################################################
"""
Demonstration zeroth-order model for WaterTAP3
"""

import numpy as np
import pandas as pd
# Import IDAES cores
from idaes.core import (declare_process_block_class, UnitModelBlockData, useDefault)
from idaes.core.util.config import is_physical_parameter_block
# Import Pyomo libraries
from pyomo.common.config import ConfigBlock, ConfigValue, In
from scipy.interpolate import interp1d
from scipy.optimize import curve_fit
from pyomo.environ import value
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import PolynomialFeatures

# Import WaterTAP# financials module
import financials
from financials import *  # ARIEL ADDED

##########################################
####### UNIT PARAMETERS ######
# At this point (outside the unit), we define the unit parameters that do not change across case studies or analyses ######.
# Below (in the unit), we define the parameters that we may want to change across case studies or analyses. Those parameters should be set as variables (eventually) and atttributed to the unit model (i.e. m.fs.UNIT_NAME.PARAMETERNAME). Anything specific to the costing only should be in  m.fs.UNIT_NAME.costing.PARAMETERNAME ######
##########################################

## REFERENCE: Cost Estimating Manual for Water Treatment Facilities (McGivney/Kawamura)

### MODULE NAME ###
module_name = "uv_aop"

# Cost assumptions for the unit, based on the method #
# this is either cost curve or equation. if cost curve then reads in data from file.
unit_cost_method = "cost_curve"
tpec_or_tic = "TPEC"
unit_basis_yr = 2014


# You don't really want to know what this decorator does
# Suffice to say it automates a lot of Pyomo boilerplate for you
@declare_process_block_class("UnitProcess")
class UnitProcessData(UnitModelBlockData):
    """
    This class describes the rules for a zeroth-order model for a unit

    The Config Block is used tpo process arguments from when the model is
    instantiated. In IDAES, this serves two purposes:
         1. Allows us to separate physical properties from unit models
         2. Lets us give users options for configuring complex units
    The dynamic and has_holdup options are expected arguments which must exist
    The property package arguments let us define different sets of contaminants
    without needing to write a new model.
    """

    CONFIG = ConfigBlock()
    CONFIG.declare("dynamic", ConfigValue(domain=In([False]), default=False, description="Dynamic model flag - must be False", doc="""Indicates whether this model will be dynamic or not,
**default** = False. Equilibrium Reactors do not support dynamic behavior."""))
    CONFIG.declare("has_holdup", ConfigValue(default=False, domain=In([False]), description="Holdup construction flag - must be False", doc="""Indicates whether holdup terms should be constructed or not.
**default** - False. Equilibrium reactors do not have defined volume, thus
this must be False."""))
    CONFIG.declare("property_package", ConfigValue(default=useDefault, domain=is_physical_parameter_block, description="Property package to use for control volume", doc="""Property parameter object used to define property calculations,
**default** - useDefault.
**Valid values:** {
**useDefault** - use default package from parent model or flowsheet,
**PhysicalParameterObject** - a PhysicalParameterBlock object.}"""))
    CONFIG.declare("property_package_args", ConfigBlock(implicit=True, description="Arguments to use for constructing property packages", doc="""A ConfigBlock with arguments to be passed to a property block(s)
and used when constructing these,
**default** - None.
**Valid values:** {
see property package for documentation.}"""))

    def build(self):
        import unit_process_equations
        return unit_process_equations.build_up(self, up_name_test=module_name)

    # NOTE ---> THIS SHOULD EVENTUaLLY BE JUST FOR COSTING INFO/EQUATIONS/FUNCTIONS. EVERYTHING ELSE IN ABOVE.
    def get_costing(self, module=financials, cost_method="wt", year=None, unit_params=None):

        if not hasattr(self.flowsheet(), "costing"):
            self.flowsheet().get_costing(module=module, year=year)

        self.costing = Block()

        time = self.flowsheet().config.time.first()
        flow_in = pyunits.convert(self.flow_vol_in[time], to_units=pyunits.m ** 3 / pyunits.hr)  # m3 /hr
        sys_cost_params = self.parent_block().costing_param
        self.costing.tpec_tic = sys_cost_params.tpec if tpec_or_tic == "TPEC" else sys_cost_params.tic

        self.costing.basis_year = unit_basis_yr

        try:
            uvt_in = unit_params['uvt_in']
            uv_dose = unit_params['uv_dose']
        except:
            uvt_in = 0.9
            uv_dose = 100

        aop = unit_params['aop']

        if aop:
            ox_dose = pyunits.convert(unit_params['dose'] * (pyunits.mg / pyunits.liter), to_units=(pyunits.kg / pyunits.m ** 3))
            chem_name = unit_params["chemical_name"][0]
            chem_dict = {chem_name: ox_dose}
            h2o2_base_cap = 1228
            h2o2_cap_exp = 0.2277
        else:
            chem_dict = {}

        self.chem_dict = chem_dict

        def power_curve(x, a, b):
            return a * x ** b

        df = pd.read_csv('data/uv_cost_interp.csv', index_col='flow')
        flow_points = [1E-8]
        flow_list = [1E-8, 1, 3, 5, 10, 25]  # flow in mgd

        for flow in flow_list[1:]:
            temp = df.loc[flow]
            cost = temp[((temp.dose == uv_dose) & (temp.uvt == uvt_in))]
            cost = cost.iloc[0]['cost']
            flow_points.append(cost)

        coeffs, cov = curve_fit(power_curve, flow_list, flow_points)
        a, b = coeffs[0], coeffs[1]

        def solution_vol_flow(flow_in):  # m3/hr
            chemical_rate = flow_in * ox_dose  # kg/hr
            chemical_rate = pyunits.convert(chemical_rate, to_units=(pyunits.lb / pyunits.day))
            soln_vol_flow = chemical_rate
            return soln_vol_flow  # lb / day

        def fixed_cap(flow_in):
            flow_in_mgd = pyunits.convert(flow_in, to_units=(pyunits.Mgallons / pyunits.day))

            uv_cap = (a * flow_in_mgd ** b) * 1E-3

            if aop:
                h2o2_cap = (h2o2_base_cap * solution_vol_flow(flow_in) ** h2o2_cap_exp) * 1E-3
            else:
                h2o2_cap = 0

            uv_aop_cap = h2o2_cap + uv_cap
            return uv_aop_cap

        def electricity():  # m3/hr
            electricity = 0.1  # kWh / m3
            return electricity

        ## fixed_cap_inv_unadjusted ##
        self.costing.fixed_cap_inv_unadjusted = Expression(expr=fixed_cap(flow_in), doc="Unadjusted fixed capital investment")  # $M

        ## electricity consumption ##
        self.electricity = electricity()  # kwh/m3

        ##########################################
        ####### GET REST OF UNIT COSTS ######
        ##########################################

        module.get_complete_costing(self.costing)
