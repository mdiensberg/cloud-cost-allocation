'''
Created on 20.04.2022

@author: marc.diensberg
'''

from configparser import ConfigParser
from logging import error
import re

from cloud_cost_allocation.cost_items import ConsumerCostItem, CostItemFactory
from cloud_cost_allocation.reader.base_reader import GenericReader


class CSV_CostAllocationKeysReader(GenericReader):
    '''
    classdocs
    '''

    __slots__ = (
        'nb_provider_meters',  # type: int
    )


    def __init__(self, cost_item_factory: CostItemFactory, config: ConfigParser):
        '''
        Constructor
        '''
        super().__init__(cost_item_factory, config)
        if 'NumberOfProviderMeters' in self.config['General']:
            self.nb_provider_meters = int(self.config['General']['NumberOfProviderMeters'])
        else:
            self.nb_provider_meters = 0

    def read_item(self, line) -> ConsumerCostItem:
        # Create item
        consumer_cost_item = self.cost_item_factory.create_consumer_cost_item()

        # Populate item
        consumer_cost_item.date_str = line['Date'].strip()
        if 'ProviderService' in line:
            consumer_cost_item.provider_service = line['ProviderService'].lower()
        if not consumer_cost_item.provider_service:
            error("Skipping cost allocation key line without ProviderService")
            return None
        if 'ProviderInstance' in line:
            consumer_cost_item.provider_instance = line['ProviderInstance'].lower()
        if not consumer_cost_item.provider_instance:
            consumer_cost_item.provider_instance = consumer_cost_item.provider_service  # Default value
        if 'Product' in line:
            consumer_cost_item.product = line['Product'].lower()
        if 'ProductMeterName' in line:
            consumer_cost_item.product_meter_name = line['ProductMeterName']
        if 'ProductMeterUnit' in line:
            consumer_cost_item.product_meter_unit = line['ProductMeterUnit']
        if 'ProductMeterValue' in line:
            consumer_cost_item.product_meter_value = line['ProductMeterValue']
        if 'ConsumerService' in line:
            consumer_cost_item.service = line['ConsumerService'].lower()
        if 'ConsumerInstance' in line:
            consumer_cost_item.instance = line['ConsumerInstance'].lower()
        # Set default values for service and instance
        if not consumer_cost_item.service:
            if consumer_cost_item.product:  # Set self-consumption, to materialize final consumption
                consumer_cost_item.service = consumer_cost_item.provider_service
                consumer_cost_item.instance = consumer_cost_item.provider_instance
            else:  # Garbage collector
                consumer_cost_item.service = self.config['General']['DefaultService'].strip()
                consumer_cost_item.instance = consumer_cost_item.service
        elif not consumer_cost_item.instance:  # Same as service by default
            consumer_cost_item.instance = consumer_cost_item.service
        if 'Dimensions' in self.config['General']:
            for dimension in self.config['General']['Dimensions'].split(','):
                consumer_dimension = 'Consumer' + dimension.strip()
                if consumer_dimension in line:
                    consumer_cost_item.dimensions[dimension] = line[consumer_dimension].lower()
        if 'ConsumerTags' in line:
            consumer_tags = line["ConsumerTags"]
            if consumer_tags:
                tags = consumer_tags.split(',')
                for tag in tags:
                    if tag:
                        key_value_match = re.match("([^:]+):([^:]*)", tag)
                        if key_value_match:
                            key = key_value_match.group(1).strip().lower()
                            value = key_value_match.group(2).strip().lower()
                            consumer_cost_item.tags[key] = value
                        else:
                            error("Unexpected consumer tag format: '" + tag + "'")
        if self.nb_provider_meters:
            for i in range(1, self.nb_provider_meters + 1):
                provider_meter_name = None
                provider_meter_unit = None
                provider_meter_value = None
                if 'ProviderMeterName%d' % i in line:
                    provider_meter_name = line['ProviderMeterName%d' % i]
                #consumer_cost_item.provider_meter_names.append(provider_meter_name)
                if 'ProviderMeterUnit%d' % i in line:
                    provider_meter_unit = line['ProviderMeterUnit%d' % i]
                #consumer_cost_item.provider_meter_units.append(provider_meter_unit)
                if 'ProviderMeterValue%d' % i in line:
                    provider_meter_value_column = 'ProviderMeterValue%d' % i
                    provider_meter_value = line[provider_meter_value_column]
                    if provider_meter_value:
                        try:
                            float(provider_meter_value)
                        except (TypeError, ValueError):
                            error("Value '" + provider_meter_value + "' of '" + provider_meter_value_column +
                                  "' of ProviderService '" + consumer_cost_item.provider_service + "'" +
                                  "is not a float")
                            provider_meter_value = None
                #consumer_cost_item.provider_meter_values.append(provider_meter_value)
                if provider_meter_name or provider_meter_unit or provider_meter_value:
                    meter = {}
                    meter['Name'] = provider_meter_name
                    meter['Unit'] = provider_meter_unit
                    meter['Value'] = provider_meter_value
                    consumer_cost_item.provider_meters.append(meter)

        consumer_cost_item.provider_cost_allocation_type = "Key"  # Default value
        if 'ProviderCostAllocationType' in line:
            consumer_cost_item.provider_cost_allocation_type = line['ProviderCostAllocationType']
            if consumer_cost_item.provider_cost_allocation_type not in ("Key", "Cost", "CloudTagSelector"):
                error("Unknown ProviderCostAllocationType '" + consumer_cost_item.provider_cost_allocation_type +
                      "' for ProviderService '" + consumer_cost_item.provider_service + "'")
                return None
        if consumer_cost_item.provider_cost_allocation_type == 'Key':
            key_str = ""
            if 'ProviderCostAllocationKey' in line and line['ProviderCostAllocationKey']:
                try:
                    key_str = line['ProviderCostAllocationKey']
                    consumer_cost_item.provider_cost_allocation_key = float(key_str)
                except (TypeError, ValueError):
                    pass
            if consumer_cost_item.provider_cost_allocation_key == 0.0:
                error("Skipping cost allocation key line with non-float " +
                      " ProviderCostAllocationKey: '" + key_str + "'" +
                      " for ProviderService '" + consumer_cost_item.provider_service + "'")
                return None
        elif consumer_cost_item.provider_cost_allocation_type == "CloudTagSelector":
            if 'ProviderCostAllocationCloudTagSelector' in line:
                consumer_cost_item.provider_cost_allocation_cloud_tag_selector = \
                    line['ProviderCostAllocationCloudTagSelector']
        if "ProviderTagSelector" in line:
            consumer_cost_item.provider_tag_selector = line["ProviderTagSelector"].lower()

        return consumer_cost_item
