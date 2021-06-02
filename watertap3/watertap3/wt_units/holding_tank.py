from pyomo.environ import Block, Expression, units as pyunits
from watertap3.utils import financials
from watertap3.wt_units.wt_unit import WT3UnitProcess

## REFERENCE
## CAPITAL:
# "Cone roof tank" costs from:
# DOE/NETL-2002/1169 - Process Equipment Cost Estimation Final Report
# Loh, H. P., Lyons, Jennifer, and White, Charles W. Process Equipment Cost Estimation, Final Report.
# United States: N. p., 2002. Web. doi:10.2172/797810.
# Regression of cost vs. capacity
# Capacity calculated based on storage time and surge capacity (user inputs)

module_name = 'holding_tank'
basis_year = 2007
tpec_or_tic = 'TPEC'


class UnitProcess(WT3UnitProcess):

    def fixed_cap(self, unit_params):
        time = self.flowsheet().config.time.first()
        self.flow_in = pyunits.convert(self.flow_vol_in[time], to_units=pyunits.m ** 3 / pyunits.hr)
        self.storage_duration = unit_params['avg_storage_time'] * pyunits.hours
        self.surge_cap = unit_params['surge_cap'] * pyunits.dimensionless
        self.capacity_needed = self.flow_in * self.storage_duration * (1 + self.surge_cap)
        # Cost curve parameters (a, b) determined from following code:
        # Data taken from WT3 Excel model
        # from scipy.optimize import curve_fit
        # def power(x, a, b):
        #     return a * x ** b
        #
        # cost_MM = [0, 0.151967998, 0.197927546, 0.366661915, 0.780071937, 1.745265206, 2.643560777, 4.656835949, 6.8784383]
        # storage_m3 = [1E-8, 191.2, 375.6, 1101.1, 3030, 8806, 16908, 29610, 37854.1]
        # coeffs, _ = curve_fit(power, storage_m3, cost_MM)
        # a, b = coeffs[0], coeffs[1]
        # print(a, b)
        self.a = 0.0001482075293096916
        self.b = 1.0143391604819805
        self.chem_dict = {}
        tank_cap = self.a * self.capacity_needed ** self.b
        return tank_cap

    def elect(self):  # m3/hr
        electricity = 0
        return electricity

    def get_costing(self, unit_params=None, year=None):
        financials.create_costing_block(self, basis_year, tpec_or_tic)
        self.costing.fixed_cap_inv_unadjusted = Expression(expr=self.fixed_cap(unit_params),
                                                           doc='Unadjusted fixed capital investment')  # $M
        self.electricity = Expression(expr=self.elect(),
                                      doc='Electricity intensity [kwh/m3]')  # kwh/m3
        financials.get_complete_costing(self.costing)

