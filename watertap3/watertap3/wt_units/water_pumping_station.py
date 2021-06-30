from pyomo.environ import Block, Expression, value, units as pyunits
from watertap3.utils import financials
from watertap3.wt_units.wt_unit import WT3UnitProcess

## REFERENCE: ADD REFERENCE HERE

module_name = 'water_pumping_station'
basis_year = 2007
tpec_or_tic = 'TPEC'

class UnitProcess(WT3UnitProcess):

    def fixed_cap(self, unit_params):
        time = self.flowsheet().config.time.first()
        self.flow_in = pyunits.convert(self.flow_vol_in[time], to_units=(pyunits.Mgallons / pyunits.day))
        pump_type = unit_params['pump_type']
        # tdh = unit_params['tdh'] * pyunits.ft
        if pump_type == 'raw':
            # Costing parameters a, b determined with the following code:
            # Data taken from WT3 excel model
            #
            # from scipy.optimize import curve_fit
            # def power(x, a, b):
            # 	return a * x ** b
            #
            # flow_lst = np.array([10, 19, 53, 79, 105, 132, 159, 185, 200])  # mgd
            # flow_cost = np.array([188032, 303010, 726314, 1050344, 1363933, 1677539, 1991145, 2299522, 2482431])  # $
            # cc, _ = curve_fit(power, flow_lst, flow_cost)
            # a, b = cc[0], cc[1]
            # print(a, b)
            self.a = 19370.357574406607
            self.b = 0.9148641590272578

        if pump_type == 'treated':
            # Costing parameters a, b determined with the following code:
            # Data taken from WT3 excel model
            #
            # from scipy.optimize import curve_fit
            # def power(x, a, b):
            # 	return a * x ** b
            #
            # flow_lst = np.array([53, 80, 106, 131, 158, 185, 211, 238, 265, 300])  # mgd
            # flow_cost = np.array([1254215, 1775451, 2271801, 2755748, 3239590, 3711029, 4107735, 4616463, 5025624, 5633425])  # $
            # cc, _ = curve_fit(power, flow_lst, flow_cost)
            # a, b = cc[0], cc[1]
            # print(a, b)
            self.a = 40073.42661387725
            self.b = 0.866701037568153
        self.chem_dict = {}
        pumping_cap = self.tpec_tic * self.a * self.flow_in ** self.b * 1E-6
        return pumping_cap

    def elect(self, unit_params):
        # Electricity costing parameters c, d determined with the following code:
        # Data taken from WT3 excel model
        # motor_eff = 0.9
        # pump_eff = 0.9
        # tdh_lst = [25, 50, 75, 100, 200, 300, 400, 1000, 2500]  # TDH in ft
        # tdh_elect = [(0.746 * 440.29 * x) / (3960 * motor_eff * pump_eff) for x in tdh_lst]
        # cc, _ = curve_fit(power_curve, tdh_lst, tdh_elect)
        # c, d = cc[0], cc[1]
        # print(c, d)
        self.c = 0.10239940765681513
        self.d = 0.9999999999999999
        flow_in_mgd = value(pyunits.convert(self.flow_in, to_units=(pyunits.Mgallons / pyunits.day)))
        flow_in_m3hr = pyunits.convert(self.flow_in, to_units=(pyunits.m ** 3 / pyunits.hr))
        self.flow_in_gpm = value(pyunits.convert(self.flow_in, to_units=(pyunits.gallons / pyunits.minute)))
        if 'pump_power' in unit_params.keys():
            self.pump_power_hp = unit_params['pump_power'] * pyunits.hp
            self.pump_power_kw = pyunits.convert(self.pump_power_hp, to_units=pyunits.kilowatts)
        else:
            self.pump_power_kw = (self.c * (flow_in_mgd / 440.29) ** self.d)
        self.pump_power_kw = self.pump_power_kw * pyunits.kilowatts
        self.elect_intens =  self.pump_power_kw / flow_in_m3hr
        return self.elect_intens

    def get_costing(self, unit_params=None, year=None):
        '''
        Initialize the unit in WaterTAP3.
        '''
        financials.create_costing_block(self, basis_year, tpec_or_tic)
        self.costing.fixed_cap_inv_unadjusted = Expression(expr=self.fixed_cap(unit_params),
                                                           doc='Unadjusted fixed capital investment')
        self.electricity = Expression(expr=self.elect(unit_params),
                                      doc='Electricity intensity [kwh/m3]')
        financials.get_complete_costing(self.costing)