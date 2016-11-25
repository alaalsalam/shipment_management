# -*- coding: utf-8 -*-
# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from __future__ import unicode_literals

import frappe
from comment_controller import CommentController
from country_code_config import get_country_code, get_country_state_code
from frappe import _
from frappe.model.mapper import get_mapped_doc
from config.app_config import FedexTestServerConfiguration, PRIMARY_FEDEX_DOC_NAME, SupportedProviderList
from provider_fedex import delete_fedex_shipment


def check_permission():
	def innerfn(fn):
		# TODO - Fix during permission pass
		# if not frappe.has_permission("DTI Shipment Note", "read"):
		# 	frappe.throw(_("Permission denied"), frappe.PermissionError)
		return fn

	return innerfn


def after_install():
	"""
	Creation Test Server Configuration for debug and testing during Application Development
	"""

	FedexConfig = frappe.new_doc("DTI Fedex Configuration")

	FedexConfig.fedex_config_name = PRIMARY_FEDEX_DOC_NAME
	FedexConfig.fedex_key = FedexTestServerConfiguration.key
	FedexConfig.password = FedexTestServerConfiguration.password
	FedexConfig.account_number = FedexTestServerConfiguration.account_number
	FedexConfig.meter_number = FedexTestServerConfiguration.meter_number
	FedexConfig.freight_account_number = FedexTestServerConfiguration.freight_account_number
	FedexConfig.use_test_server = FedexTestServerConfiguration.use_test_server

	FedexConfig.submit()


class ShipmentNoteOperationalStatus(object):
	InProgress = "In progress"
	Completed = "Completed"
	Returned = "Returned"
	Cancelled = "Cancelled"
	Failed = "Failed"


##############################################################################

# Mapper

@check_permission()
@frappe.whitelist()
def make_new_shipment_note_from_delivery_note(source_name, target_doc=None):
	doclist = get_mapped_doc("Delivery Note", source_name, {
		"Delivery Note": {
			"doctype": "DTI Shipment Note",
			"field_map": {
				"name": "delivery_note",
			}
		}
	}, target_doc)

	return doclist


@check_permission()
@frappe.whitelist()
def make_fedex_shipment_from_shipment_note(source_name, target_doc=None):
	doclist = get_mapped_doc("DTI Shipment Note", source_name, {
		"DTI Shipment Note": {
			"doctype": "DTI Fedex Shipment",
			"field_map": {
				"name": "shipment_note_link"
			}
		}
	}, target_doc)

	return doclist


##############################################################################


@check_permission()
@frappe.whitelist()
def get_carriers_list():
	return [SupportedProviderList.Fedex]


##############################################################################


class Contact(object):
	def __init__(self):
		self.PersonName = None
		self.CompanyName = None
		self.PhoneNumber = None
		self.Email_List = []


class Address(object):
	def __init__(self):
		self.StreetLines = []
		self.City = None
		self.StateOrProvinceCode = None
		self.PostalCode = None
		self.Country = None
		self.CountryCode = None


class RequestedShipment(object):
	def __init__(self):
		self.address = Address()
		self.contact = Contact()

	def __str__(self):
		return """
		Contact PersonName            = {0}
		Contact CompanyName           = {1}
		Contact PhoneNumber           = {2}
		Email list                    = {3}
		___________________________________________

		Address StreetLines           = {4}
		Address City                  = {5}
		Address StateOrProvinceCode   = {6}
		Address PostalCode            = {7}
		Address Country               = {8}
		Address CountryCode           = {9} """.format(self.contact.PersonName,
													   self.contact.CompanyName,
													   self.contact.PhoneNumber,
													   self.contact.Email_List,
													   self.address.StreetLines,
													   self.address.City,
													   self.address.StateOrProvinceCode,
													   self.address.PostalCode,
													   self.address.Country,
													   self.address.CountryCode)


@check_permission()
@frappe.whitelist()
def get_shipper(delivery_note_name):

	shipper = RequestedShipment()

	delivery_note = frappe.db.sql('''SELECT * from `tabDelivery Note` WHERE name="%s"''' % delivery_note_name, as_dict=True)

	if delivery_note[0].company:
		shipper.contact.PersonName = delivery_note[0].company
		shipper.contact.CompanyName = delivery_note[0].company

		company = frappe.db.sql('''SELECT *  from tabCompany WHERE name="%s"''' % delivery_note[0].company, as_dict=True)

		if company:
			if company[0].phone_no:
				shipper.contact.PhoneNumber = company[0].phone_no

			if company[0].country:
				shipper.address.Country = company[0].country
				shipper.address.CountryCode = get_country_code(shipper.address.Country)

			company_address = frappe.db.sql('''SELECT * from tabAddress WHERE company="%s" AND is_your_company_address=1''' % delivery_note[0].company, as_dict=True)

			if company_address:
				if company_address[0].address_line1:
					shipper.address.StreetLines.append(company_address[0].address_line1)

				if company_address[0].address_line2:
					shipper.address.StreetLines.append(company_address[0].address_line2)

				if company_address[0].city:
					shipper.address.City = company_address[0].city

				if company_address[0].pincode:
					shipper.address.PostalCode = company_address[0].pincode

				if company_address[0].state:
					shipper.address.StateOrProvinceCode = get_country_state_code(country=shipper.address.Country,
																				   state=shipper[0].state)

	return shipper


@check_permission()
@frappe.whitelist()
def get_recipient(delivery_note_name):

	recipient = RequestedShipment()

	recipient.contact.PersonName = frappe.db.sql('''SELECT customer_name from `tabDelivery Note` WHERE name="%s"''' % delivery_note_name, as_dict=True)[0].customer_name

	recipient.contact.CompanyName = frappe.db.sql('''SELECT * from tabCustomer WHERE name="%s"''' % recipient.contact.PersonName, as_dict=True)[0].name

	shipping_address = frappe.db.sql('''SELECT * from tabAddress WHERE customer_name="%s" AND is_shipping_address=1''' % recipient.contact.PersonName, as_dict=True)
	primary_contact = frappe.db.sql('''SELECT * from tabContact WHERE customer="%s" and is_primary_contact=1''' % recipient.contact.PersonName, as_dict=True)

	if shipping_address:
		if shipping_address[0].phone:
			recipient.contact.PhoneNumber = shipping_address[0].phone

		if shipping_address[0].email_id:
			recipient.contact.Email_List.append(shipping_address[0].email_id)

		if shipping_address[0].address_line1:
			recipient.address.StreetLines.append(shipping_address[0].address_line1)

		if shipping_address[0].address_line2:
			recipient.address.StreetLines.append(shipping_address[0].address_line2)

		if shipping_address[0].city:
			recipient.address.City = shipping_address[0].city

		if shipping_address[0].pincode:
			recipient.address.PostalCode = shipping_address[0].pincode

		if shipping_address[0].country:
			recipient.address.Country = shipping_address[0].country
			recipient.address.CountryCode = get_country_code(recipient.address.Country)
			recipient.address.StateOrProvinceCode = get_country_state_code(country=recipient.address.Country, state=shipping_address[0].state)

	if primary_contact:
		if not recipient.contact.PhoneNumber:
			recipient.contact.PersonName = "{} {}".format(primary_contact[0].first_name, primary_contact[0].last_name)
			recipient.contact.PhoneNumber = primary_contact[0].phone

		if primary_contact[0].email_id:
			recipient.contact.Email_List.append(primary_contact[0].email_id)

	return recipient


##############################################################################


@check_permission()
@frappe.whitelist()
def get_delivery_items(delivery_note_name):
	return frappe.db.sql('''SELECT * from `tabDelivery Note Item` WHERE parent="%s"''' % delivery_note_name, as_dict=True)


@check_permission()
@frappe.whitelist()
def cancel_shipment(source_name):
	shipment = frappe.get_doc('DTI Shipment Note', source_name)

	frappe.db.set(shipment, "shipment_note_status", ShipmentNoteOperationalStatus.Cancelled)

	if shipment.shipment_provider == 'FEDEX':
		delete_fedex_shipment(source_doc=source_name)
		CommentController.add_comment('DTI Shipment Note',
									  source_name,
									  CommentController.Comment,
									  "Shipment has been cancelled.")
