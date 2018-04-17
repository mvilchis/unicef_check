import configparser
from datetime import datetime, timedelta

import requests
from dateutil.parser import parse
from dateutil.relativedelta import relativedelta
from temba_client.v2 import TembaClient

###################    Read configuration    ####################
config = configparser.ConfigParser()
config.read('keys.ini')
TOKEN_MX = config['rapidpro']['RAPIDPRO_TOKEN']

#UNICEF_ENDPOINT = config['unicef']['UNICEF_ENDPOINT']
UNICEF_ENDPOINT = "http://localhost:5000/"

MIALERTA_FLOW = "07d56699-9cfb-4dc6-805f-775989ff5b3f"
MIALERTA_NODE = "response_1"
CANCEL_FLOW = "dbd5738f-8700-4ece-8b8c-d68b3f4529f7"
CANCEL_NODE = "response_3"


mx_client = TembaClient('rapidpro.datos.gob.mx', TOKEN_MX)

###############################################################################
#                           Auxiliar functions                                #
###############################################################################


def get_active_states(contacts):
    states = {}
    for c in contacts:
        key = c.fields["rp_state_number"]
        if key:
            states[key] = 0
    return states


def get_value_by_key(result, key):
    items = [
        item for item in result["response"]
        if ("group" in item and item["group"] == key) or (
            "key" in item and item["key"] == key)
    ]
    return items[0]["count"]


###############################################################################
#                             User functions                                  #
###############################################################################
def check_users(contacts, start_date=None, end_date=None):
    """ Endpoints to check:
        * users_by_type
    """
    result = requests.get(UNICEF_ENDPOINT + "users_by_type").json()
    # Check babies
    puerperium = [
        c for c in contacts if any(("PUERPERIUM" in g.name for g in c.groups))
    ]
    puerperium_group_flag = [
        c for c in contacts
        if c.fields["rp_ispregnant"] == "0" and any(("PUERPERIUM" in g.name
                                                     for g in c.groups))
    ]
    print ("grupo: %d, bandera %d" % (len(puerperium), len(puerperium_group_flag)))

    # Check pregnants
    pregnant = [
        c for c in contacts if any(("PREGNANT" in g.name for g in c.groups))
    ]
    pregnant_group_flag = [
        c for c in contacts
        if c.fields["rp_ispregnant"] == "1" and any(("PREGNANT" in g.name
                                                     for g in c.groups))
    ]
    print ("grupo %d, bandera %d" %(len(pregnant), len(pregnant_group_flag)))
    l = list(set(puerperium) - set(puerperium_group_flag))
    print (l[0].uuid)
    # Check personal
    personal = [
        c for c in contacts
        if any(("PERSONAL" in g.name
                for g in c.groups)) and not (any(("ALTO_PERSONAL" in g.name
                                                  for g in c.groups)))
    ]

    assert (len(pregnant_group_flag) == get_value_by_key(result, "pregnant"))
    assert (len(puerperium) == get_value_by_key(result, "baby"))
    assert (len(personal) == get_value_by_key(result, "personal"))


def check_users_by_state(contacts, start_date=None, end_date=None):
    """ Endpoints to check:
        * users_by_state
    """
    result = requests.get(UNICEF_ENDPOINT + "users_by_state").json()
    states = get_active_states(contacts)
    for c in contacts:
        key = c.fields["rp_state_number"]
        if key:
            if key in states:
                states[key] += 1
            else:
                states[key] = 1
    for key in states.keys():
        api_value = get_value_by_key(result, key)
        if api_value != states[key]:
            print("%s- %s" % (states[key], api_value))
        assert (api_value == states[key])


def check_users_by_mun(contacts, start_date=None, end_date=None):
    states = get_active_states(contacts)
    for state in states.keys():
        result = requests.get(
            UNICEF_ENDPOINT + "users_by_mun?state=" + state).json()
        mun = {}
        for c in contacts:
            this_state = c.fields["rp_state_number"]
            key = c.fields["rp_mun"]
            if this_state and this_state == state and key:
                if key in mun:
                    mun[key] += 1
                else:
                    mun[key] = 1
        for key in mun.keys():
            api_value = get_value_by_key(result, key)
            if api_value != mun[key]:
                print("(%s-%s):%s-%s" % (state, key, mun[key], api_value))
            assert (api_value == mun[key])


def check_users_by_mom_age(contacts, start_date=None, end_date=None):
    result = requests.get(UNICEF_ENDPOINT + "users_by_mom_age").json()
    first = "0.0-19.0"
    second = "19.0-35.0"
    third = "35.0-*"
    ages = {first:0,
            second:0,
            third:0}
    for c in contacts:
        is_pregnant = any(("PREGNANT" in g.name for g in c.groups))
        is_puerperium = any(("PUERPERIUM" in g.name for g in c.groups))
        mom_age_str = c.fields["rp_mamafechanac"]
        parto_str = c.fields["rp_deliverydate"] if is_puerperium else c.fields["rp_duedate"]
        if not mom_age_str or not parto_str or not (is_pregnant or is_puerperium):
            continue
        is_date =  any(char.isdigit() for char in mom_age_str)
        parto_str = parto_str[:-1] if parto_str[-1] == "." else parto_str
        is_date_parto =  any(char.isdigit() for char in parto_str)
        if  is_date and is_date_parto:
            mom_age = parse(mom_age_str).replace(tzinfo=None)
            parto = parse(parto_str).replace(tzinfo=None)
            diff = (parto - mom_age).days/365.25
            if diff <= 19:
                ages[first] +=1
            if diff >= 35:
                ages[third] += 1
            if diff > 19 and diff < 35:
                ages[second] += 1
    total_users = sum([ages[k] for k in ages.keys()])
    ten_percent = total_users * .1
    for key in ages.keys():
        api_value = get_value_by_key(result, key)
        assert(api_value == ages[key] or 
               (api_value <= ages[key]+ten_percent and 
               api_value >= ages[key] - ten_percent))

def check_users_by_hospital(contacts, start_date=None, end_date=None):
    hospitals = {}
    result = requests.get(UNICEF_ENDPOINT + "users_by_hospital").json()
    for c in contacts:
        key = c.fields["rp_atenmed"]
        if not key:
            continue
        if key in hospitals:
            hospitals[key] +=1
        else:
            hospitals[key] = 1
    for key in hospitals.keys():
        api_value = get_value_by_key(result, key)
        assert (api_value == hospitals[key])

def check_users_by_channels(contacts, start_date=None, end_date=None):
    channels = {"sms": 0, "facebook":0, "twitter":0, "others":0}
    result = requests.get(UNICEF_ENDPOINT + "users_by_channel").json()
    for c in contacts:
        is_sms = any ("tel:" in u for u in c.urns)
        is_fb  = any ("facebook" in u for u in c.urns)
        is_twitter  = any ("twitterid" in u for u in c.urns)
        if is_sms:
            channels["sms"] +=1
        elif is_fb:
            channels["facebook"] +=1
        elif is_twitter:
            channels["twitter"] +=1
        else:
            channels["others"] +=1
    for key in channels.keys():
        api_value = get_value_by_key(result, key)
        assert (api_value == channels[key])

            
def get_contacts_by_group(contacts, group):
    list_group = []
    for c in contacts:
        groups = [g.name for g in c.groups]
        if group in groups:
            list_group.append(c)
    return list_group


def check_babies(contacts, start_date=None, end_date=None):
    pass


def main():
    pass
    #contacts  = mx_client.get_contacts(group="ALL").all()
    #after = datetime.utcnow() - timedelta(days=2)
    #after = after.isoformat()
    #runs = mx_client.get_runs(after=after).all()
    #runs += mx_client.get_runs(flow=MIALERTA_FLOW).all()
    #runs += mx_client.get_runs(flow=CANCEL_FLOW).all()



if __name__ == '__main__':
    main()
