#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Feb 16 09:17:59 2021

@author: ksitterl
"""

# Import Pyomo libraries
from pyomo.common.config import ConfigBlock, ConfigValue, In
from pyomo.environ import Block, Constraint, Var, units as pyunits
from pyomo.network import Port
from unit_process_equations import initialization

# Import IDAES cores
from idaes.core import (declare_process_block_class,
                        UnitModelBlockData,
                        useDefault)
from idaes.core.util.config import is_physical_parameter_block

from pyomo.environ import (
    Expression, Var, Param, NonNegativeReals, units as pyunits)

# Import WaterTAP# financials module
import financials
from financials import *

from pyomo.environ import ConcreteModel, SolverFactory, TransformationFactory
from pyomo.network import Arc
from idaes.core import FlowsheetBlock

# Import properties and units from "WaterTAP Library"
from water_props import WaterParameterBlock

import generate_constituent_list
train_constituent_list = generate_constituent_list.run()
train_constituent_removal_factors = generate_constituent_list.get_removal_factors("hcl_addition")

flow_recovery_factor = 0.99999 # TODO

basis_year = 2007
fixed_op_cost_scaling_exp = 0.7


# You don't really want to know what this decorator does
# Suffice to say it automates a lot of Pyomo boilerplate for you
@declare_process_block_class("UnitProcess")
class UnitProcessData(UnitModelBlockData):
       
    """
    This class describes the rules for a zeroth-order model for a unit
    """
    # The Config Block is used tpo process arguments from when the model is
    # instantiated. In IDAES, this serves two purposes:
    #     1. Allows us to separate physical properties from unit models
    #     2. Lets us give users options for configuring complex units
    # For WaterTAP3, this will mainly be boilerplate to keep things consistent
    # with ProteusLib and IDAES.
    # The dynamic and has_holdup options are expected arguments which must exist
    # The property package arguments let us define different sets of contaminants
    # without needing to write a new model.
    CONFIG = ConfigBlock()
    CONFIG.declare("dynamic", ConfigValue(
        domain=In([False]),
        default=False,
        description="Dynamic model flag - must be False",
        doc="""Indicates whether this model will be dynamic or not,
**default** = False. Equilibrium Reactors do not support dynamic behavior."""))
    CONFIG.declare("has_holdup", ConfigValue(
        default=False,
        domain=In([False]),
        description="Holdup construction flag - must be False",
        doc="""Indicates whether holdup terms should be constructed or not.
**default** - False. Equilibrium reactors do not have defined volume, thus
this must be False."""))
    CONFIG.declare("property_package", ConfigValue(
        default=useDefault,
        domain=is_physical_parameter_block,
        description="Property package to use for control volume",
        doc="""Property parameter object used to define property calculations,
**default** - useDefault.
**Valid values:** {
**useDefault** - use default package from parent model or flowsheet,
**PhysicalParameterObject** - a PhysicalParameterBlock object.}"""))
    CONFIG.declare("property_package_args", ConfigBlock(
        implicit=True,
        description="Arguments to use for constructing property packages",
        doc="""A ConfigBlock with arguments to be passed to a property block(s)
and used when constructing these,
**default** - None.
**Valid values:** {
see property package for documentation.}"""))
    
    
    #unit_process_equations.get_base_unit_process()
    from unit_process_equations import initialization

    
    def build(self):
        import unit_process_equations
        return unit_process_equations.build_up(self, up_name_test="hcl_addition")
    
    
    def get_costing(self, module=financials, cost_method="wt", year=None):
        """
        We need a get_costing method here to provide a point to call the
        costing methods, but we call out to an external costing module
        for the actual calculations. This lets us easily swap in different
        methods if needed.

        Within IDAES, the year argument is used to set the initial value for
        the cost index when we build the model.
        """
        # First, check to see if global costing module is in place
        # Construct it if not present and pass year argument
        if not hasattr(self.flowsheet(), "costing"):
            self.flowsheet().get_costing(module=module, year=year)

        # Next, add a sub-Block to the unit model to hold the cost calculations
        # This is to let us separate costs from model equations when solving
        self.costing = Block()
        
        def _make_vars(self):
            # build generic costing variables (all costing models need these vars)
            self.base_cost = Var(initialize=1e5,
                                 domain=NonNegativeReals,
                                 doc='Unit Base Cost cost in $')
            self.purchase_cost = Var(initialize=1e4,
                                     domain=NonNegativeReals,
                                     doc='Unit Purchase Cost in $')
    
    
        # Build a costing method for each type of unit
        def up_costing(self, cost_method="wt"):
            
            '''
            This is where you create the variables and equations specific to each unit.
            This method should mainly consider capital costs for the unit - operating
            most costs should done for the entire flowsheet (e.g. common utilities).
            Unit specific operating costs, such as chemicals, should be done here with
            standard names that can be collected at the flowsheet level.

            You can access variables from the unit model using:

                self.parent_block().variable_name

            You can also have unit specific parameters here, which could be retrieved
            from the spreadsheet
            '''
            # Based on costs for H2SO4 addition from McGivney/Kawamura 
            
            time = self.parent_block().flowsheet().config.time.first()
            flow_in = pyunits.convert(self.parent_block().flow_vol_in[time],
                                      to_units=pyunits.m**3 / pyunits.hour) # m3 /hr
            
            cost_method = 'wt'
            tpec_or_tic = 'TPEC'
            number_of_units = 2
            lift_height = 100*pyunits.ft # ft
            
            hcl_dose = 0.03 * (pyunits.kg / pyunits.m**3) # kg/m3
            hcl_flow_rate = flow_in * hcl_dose # kg/hr
            print(f'\n\nhcl_flow_rate before conversion is: {hcl_flow_rate}\n\n')
            hcl_flow_rate = pyunits.convert(hcl_flow_rate, to_units=(pyunits.kg / pyunits.day))
            print(f'\n\nhcl_flow_rate after conversion is: {hcl_flow_rate}\n\n')
            density_of_solution = 1490 * (pyunits.kg / pyunits.m**3)# kg/m3
            # ratio_in_solution = 0.5 # 
            solution_vol_flow = hcl_flow_rate / density_of_solution # m3/day
            base_fixed_cap_cost = 1.95 
            cap_scaling_exp = 0.6179
            pump_eff = 0.9
            motor_eff = 0.9
            
            def tpec_tic(tpec_or_tic):
                return 3.4 if tpec_or_tic == 'TPEC' else 1.65
                
            
            
            def fixed_cap(flow_in, hcl_flow_rate, solution_vol_flow): # m3/hr
                
                solution_vol_flow = pyunits.convert(solution_vol_flow, to_units=(pyunits.gallon / pyunits.day)) #gpd
                source_cost = 900.97 * solution_vol_flow ** cap_scaling_exp
                hcl_cap = source_cost * tpec_tic(tpec_or_tic) * number_of_units * 1E-6 # M$
                return hcl_cap
              
            
            def electricity(flow_in, hcl_flow_rate, solution_vol_flow): 
                
                solution_vol_flow = pyunits.convert(solution_vol_flow, to_units=(pyunits.gallon / pyunits.minute))
                electricity = (0.746 * solution_vol_flow * lift_height / (3960 * pump_eff * motor_eff)) / flow_in # kWh/m3
                return electricity
            
            

            _make_vars(self)

            self.base_fixed_cap_cost = Param(mutable=True,
                                             initialize=base_fixed_cap_cost,
                                             doc="Some parameter from TWB")
            self.cap_scaling_exp = Param(mutable=True,
                                         initialize=cap_scaling_exp,
                                         doc="Another parameter from TWB")

            

            ################### TWB METHOD ###########################################################
            if cost_method == "twb":
                    self.fixed_cap_inv_unadjusted = Expression(
                        expr=self.base_fixed_cap_cost *
                        flow_in ** self.cap_scaling_exp,
                        doc="Unadjusted fixed capital investment")
            ##############################################################################

            ################## WATERTAP METHOD ###########################################################
            if cost_method == "wt":

                # cost index values - TODO MOVE THIS TO TOP
                df = get_ind_table()
                self.cap_replacement_parts = df.loc[basis_year].Capital_Factor
                self.catalysts_chemicals = df.loc[basis_year].CatChem_Factor
                self.labor_and_other_fixed = df.loc[basis_year].Labor_Factor
                self.consumer_price_index = df.loc[basis_year].CPI_Factor

                # capital costs (unit: MM$) ---> TCI IN EXCEL
                self.fixed_cap_inv_unadjusted = Expression(
                    expr=fixed_cap(flow_in, hcl_flow_rate, solution_vol_flow),
                    doc="Unadjusted fixed capital investment") # $M

                self.fixed_cap_inv = self.fixed_cap_inv_unadjusted * self.cap_replacement_parts
                self.land_cost = self.fixed_cap_inv * land_cost_precent_FCI
                self.working_cap = self.fixed_cap_inv * working_cap_precent_FCI
                self.total_cap_investment = self.fixed_cap_inv + self.land_cost + self.working_cap

                # variable operating costs (unit: MM$/yr) -> MIKE TO DO -> ---> CAT+CHEM IN EXCEL
                # --> should be functions of what is needed!?
                # cat_chem_df = pd.read_csv('catalyst_chemicals.csv')
                # cat_and_chem = flow_in * 365 * on_stream_factor # TODO
                self.electricity = electricity(flow_in, hcl_flow_rate, solution_vol_flow) # kwh/m3 
                cat_chem_df = pd.read_csv('data/catalyst_chemicals.csv', index_col="Material")
                chem_cost_sum = 0 
                
                chem_dic = {"Hydrochloric_Acid_(HCl)": hcl_dose}
                
                for key in chem_dic.keys():
                    chem_cost = cat_chem_df.loc[key].Price # $ / kg 
                    chem_cost_sum = chem_cost_sum + (flow_in * chem_cost * self.catalysts_chemicals * chem_dic[key] * 365 * 24 * 1E-6) #
                
                self.cat_and_chem_cost = chem_cost_sum 
                
                flow_in_m3yr = (pyunits.convert(self.parent_block().flow_vol_in[time], to_units=pyunits.m**3/pyunits.year))
                self.electricity_cost = Expression(
                        expr= (self.electricity * flow_in_m3yr * elec_price * 1E-6),
                        doc="Electricity cost") # M$/yr
                self.other_var_cost = 0 
               
                self.base_employee_salary_cost = self.fixed_cap_inv_unadjusted * salaries_percent_FCI
                self.salaries = Expression(
                        expr= self.labor_and_other_fixed * self.base_employee_salary_cost,
                        doc="Salaries")
                
                self.benefits = self.salaries * benefit_percent_of_salary
                self.maintenance = maintinance_costs_precent_FCI * self.fixed_cap_inv
                self.lab = lab_fees_precent_FCI * self.fixed_cap_inv
                self.insurance_taxes = insurance_taxes_precent_FCI * self.fixed_cap_inv
                self.total_fixed_op_cost = Expression(
                    expr = self.salaries + self.benefits + self.maintenance + self.lab + self.insurance_taxes)

                self.total_up_cost = (
                    self.total_cap_investment
                    + self.cat_and_chem_cost
                    + self.electricity_cost
                    + self.other_var_cost
                    + self.total_fixed_op_cost)
    
        up_costing(self.costing, cost_method=cost_method)
          
        
# OTHER CALCS

def create(m, up_name):
    
    # Set removal and recovery fractions
    getattr(m.fs, up_name).water_recovery.fix(flow_recovery_factor)
    
    for constituent_name in getattr(m.fs, up_name).config.property_package.component_list:
        
        if constituent_name in train_constituent_removal_factors.keys():
            getattr(m.fs, up_name).removal_fraction[:, constituent_name].fix(train_constituent_removal_factors[constituent_name])
        else:
            getattr(m.fs, up_name).removal_fraction[:, constituent_name].fix(0)

    # Also set pressure drops - for now I will set these to zero
    getattr(m.fs, up_name).deltaP_outlet.fix(1e-4)
    getattr(m.fs, up_name).deltaP_waste.fix(1e-4)

    # Adding costing for units - this is very basic for now so use default settings
    getattr(m.fs, up_name).get_costing(module=financials)

    return m       