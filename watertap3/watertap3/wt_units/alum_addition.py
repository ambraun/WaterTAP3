from pyomo.environ import Block, Expression, units as pyunits
from watertap3.utils import financials
from watertap3.wt_units.wt_unit import WT3UnitProcess

## REFERENCE
## CAPITAL:
# Based on costs for LIQUID ALUM FEED - FIGURE 5.5.6
# Cost Estimating Manual for Water Treatment Facilities (McGivney/Kawamura) (2008)
# DOI:10.1002/9780470260036
## ELECTRICITY:

module_name = 'alum_addition'
basis_year = 2007
tpec_or_tic = 'TPEC'


class UnitProcess(WT3UnitProcess):

    def get_costing(self, unit_params=None, year=None):
        self.costing = Block()
        self.costing.basis_year = basis_year
        sys_cost_params = self.parent_block().costing_param
        self.tpec_or_tic = tpec_or_tic
        if self.tpec_or_tic == 'TPEC':
            self.costing.tpec_tic = tpec_tic = sys_cost_params.tpec
        else:
            self.costing.tpec_tic = tpec_tic = sys_cost_params.tic

        '''
        We need a get_costing method here to provide a point to call the
        costing methods, but we call out to an external consting module
        for the actual calculations. This lets us easily swap in different
        methods if needed.

        Within IDAES, the year argument is used to set the initial value for
        the cost index when we build the model.
        '''
        time = self.flowsheet().config.time.first()
        flow_in = pyunits.convert(self.flow_vol_in[time], to_units=pyunits.m ** 3 / pyunits.hr)

        number_of_units = 2
        lift_height = 100 * pyunits.ft
        pump_eff = 0.9 * pyunits.dimensionless
        motor_eff = 0.9 * pyunits.dimensionless

        base_fixed_cap_cost = 15408
        cap_scaling_exp = 0.5479

        chem_name = 'Aluminum_Al2_SO4_3'
        chemical_dosage = pyunits.convert(unit_params['dose'] * (pyunits.mg / pyunits.liter), to_units=(pyunits.kg / pyunits.m ** 3))  # kg/m3
        solution_density = 1360 * (pyunits.kg / pyunits.m ** 3)  # kg/m3
        ratio_in_solution = 0.50
        self.chem_dict = {chem_name: chemical_dosage}

        def solution_vol_flow(flow_in):  # m3/hr
            chemical_rate = flow_in * chemical_dosage  # kg/hr
            chemical_rate = pyunits.convert(chemical_rate, to_units=(pyunits.kg / pyunits.day))
            soln_vol_flow = chemical_rate / solution_density / ratio_in_solution
            soln_vol_flow = pyunits.convert(soln_vol_flow, to_units=(pyunits.gallon / pyunits.day))
            return soln_vol_flow  # gal/day

        def fixed_cap(flow_in):
            source_cost = base_fixed_cap_cost * solution_vol_flow(flow_in) ** cap_scaling_exp
            alum_cap = (source_cost * tpec_tic * number_of_units) * 1E-6
            return alum_cap

        def electricity(flow_in):  # m3/hr
            soln_vol_flow = pyunits.convert(solution_vol_flow(flow_in), to_units=(pyunits.gallon / pyunits.minute))
            electricity = (0.746 * soln_vol_flow * lift_height / (3960 * pump_eff * motor_eff)) / flow_in  # kWh/m3
            return electricity

        self.costing.fixed_cap_inv_unadjusted = Expression(expr=fixed_cap(flow_in),
                                                           doc='Unadjusted fixed capital investment')  # $M

        self.electricity = electricity(flow_in)  # kwh/m3

        financials.get_complete_costing(self.costing)