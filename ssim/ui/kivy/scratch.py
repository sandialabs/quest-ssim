a = {'Configuration 1': ['NewBESS_charge_kw', 'NewBESS_discharge_kw'],
     'Configuration 2': ['NewBESS_charge_kw', 'NewBESS_discharge_kw']}

b = {'Configuration 1': [],
     'Configuration 2': []}

test_dict = b

# iterate through each item in the dict
# if the lists of all keys are empty send message

empty_flag = True
for config, config_variables in test_dict.items():
    if config_variables != []:
        empty_flag = False
    
print(empty_flag)
