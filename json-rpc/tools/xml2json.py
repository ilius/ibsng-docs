#!/usr/bin/env python3

import sys
import json
import os
from os.path import join

from lxml import etree
from lxml.etree import _Element as Element
from lxml.etree import tostring

import jsbeautifier

paramTypeMapping = {
	"str": ("string", ""),
	"srt": ("string", ""),

	"str_int": ("string", ""),

	"int": ("number", ""),
	"float": ("number", ""),

	"datetime": ("string", "datetime"),
	"datetime, float": ("string", "datetime or number"),
	"str_datetime": ("string", "datetime"),
	"str_datetime, float": ("string", "datetime or number"),

	"bool": ("boolean", ""),
	"true_if_exists": ("boolean", "true if exists"),

	"list": ("array", ""),
	"list, str": ("array", ""),

	"dict": ("object", ""),

	"null": ("null", ""),
	
	"int|null": ("int", "int or null"),
	"dynamic": ("", "dynamic type"),
}


def toStr(elem):
	return tostring(
		elem,
		method="html",
		pretty_print=True,
	).decode("utf-8")


# options = jsbeautifier.default_options()
# options.indent_size = 2
# ['collapse', 'expand', 'end-expand', 'none', 'preserve-inline']

# options.brace_style = "none"
# options.keep_array_indentation = False

# class CustomJSONEncoder(json.JSONEncoder):
# 	def iterencode(self, obj, _one_shot=False):
# 		print(type(obj))
# 		if isinstance(obj, list):
# 			print(obj)
# 			if not obj:
# 				return "[]"
# 			if isinstance(obj[0], str) and len(obj) < 4:
# 				return json.dumps(obj)
# 		return super().iterencode(obj, _one_shot=_one_shot)

# encoder = CustomJSONEncoder()
# encoder.indent = 2
# encoder.item_separator = ','
# encoder.key_separator = ': '

def dataToPrettyJson(data):
	# return encoder.encode(data)
	# return jsbeautifier.beautify(json.dumps(data), options)
	return json.dumps(
		data,
		sort_keys=False,
		indent=2,
		ensure_ascii=True,
	)


def getChoiceJsonParam(param: "Element") -> dict:
	paramName = param.attrib.get("name")
	description = param.attrib.get("comment")
	values = []
	comments = {}
	for choiceElem in param.getchildren():
		if choiceElem.tag != "choice":
			print(f"expected choice tag, got {toStr(choiceElem)}")
			return
		value = choiceElem.attrib.get("value")
		if value is None:
			print(f"choice with no value: {toStr(choiceElem)}")
			return
		values.append(value)
		comment = choiceElem.attrib.get("comment")
		if comment:
			comments[value] = comment
	paramJson = {}
	if paramName:
		paramJson["name"] = paramName
	if description is not None:
		paramJson["description"] = description
	paramJson["value"] = values
	if comments:
		paramJson["value_comment"] = comments
	return paramJson



def getListItemSchema(item: "Element") -> "dict | list":
	# possible keys for itemSchema: title, type, required: list[str], properties: dict
	_type = item.attrib.get("type")
	if not _type:
		print(f"item has no type: {toStr(item)}")
		return
	if _type == "choice":
		itemJson = getChoiceJsonParam(item)
		if itemJson is None:
			return
		itemJson["title"] = ""
	return {
		"title": "",
		"type": _type,
	}

def getListSchema(elem: "Element") -> "dict | list":
	schema = {
		"type": "array",
	}
	items = elem.findall("item")
	if items:
		if len(items) > 1:
			print(items)
		itemSchema = getListItemSchema(items[0])
		if itemSchema:
			schema["items"] = itemSchema

	length = elem.attrib.get("length")
	if length and length != "-1":
		schema["length"] = length
	return schema




def getJsonParam(param: "Element") -> dict:
	paramName = param.attrib.get("name")

	paramType = param.attrib.get("type")
	if not paramType:
		print(f"{branch=}: param type is empty: {toStr(param)}")
		return

	if paramType == "choice":
		return getChoiceJsonParam(param)

	newParamType, typeComment = paramTypeMapping[paramType]
	if not newParamType:
		print(f"invalid param type {paramType}")
		newParamType = "string"

	description = param.attrib.get("comment", "")
	if typeComment:
		description = typeComment + ", " + description

	if newParamType == "array":
		schema = getListSchema(param)
	else:
		schema = {
			"type": newParamType,
		}		
	paramJson = {}
	if paramName:
		paramJson["name"] = paramName
	paramJson.update({
		"description": description,
		"schema": schema,
	})
	if param.attrib.get("optional"):
		paramJson["optional"] = True
	return paramJson


def getJsonMethod(handlerName: str, method: "Element", authTypes: list[str]):
	if method.tag != "method":
		# print(f"expected method element, got {method.tag}: {method}")
		return
	methodName = method.attrib.get("name")
	if not methodName:
		print(f"method has no name: {toStr(method)}")
		return
	inputElem = method.find("input")
	if inputElem is None:
		print(f"no <input> for: {toStr(method)}")
		return
	outputElem = method.find("output")
	if outputElem is None:
		print(f"{branch=}, no <output> for: {toStr(method)}")
		return
	params = []
	for param in inputElem.getchildren():
		if param.tag != "param":
			continue
		if not param.attrib.get("name"):
			print(f"{branch=}: param name is empty: {toStr(param)}")
			continue
		jsonParam = getJsonParam(param)
		if jsonParam is None:
			continue
		params.append(jsonParam)
	jsonMethod = {
		"name": handlerName + "." + methodName,
		"description": method.attrib.get("comment", ""),
		"auth_type": authTypes,
	}
	requires_perm = method.attrib.get("requires_perm")
	if requires_perm:
		jsonMethod["requires_perm"] = requires_perm
	jsonMethod["params"] = params
	outputComment = outputElem.attrib.get("comment", "")
	outputType = outputElem.attrib.get("type")
	outputValue = outputElem.attrib.get("value")
	resultType: "str | None" = None
	resultValues: "list | None" = None
	if outputValue:
		resultValues = [outputValue]
	elif not outputType:
		print(f"no output type nor value: {branch=}: {toStr(method)}")
		return None
	if outputType == "choice":
		resultValues = []
		for param in outputElem.getchildren():
			if param.tag != "choice":
				print(f"expected choice tag, got: {toStr(param)}")
				continue
			value = param.attrib.get("value")
			if not value:
				print("empty value in {toStr(param)}")
				continue
			resultValues.append(value)
	elif outputType:
		resultType, typeComment = paramTypeMapping[outputType]
	resultItems = []
	for param in outputElem.getchildren():
		if param.tag != "param":
			continue
		if not param.attrib.get("name"):
			print(f"{branch=}: param name is empty: {toStr(param)}")
			continue
		jsonParam = getJsonParam(param)
		if jsonParam is None:
			continue
		resultItems.append(jsonParam)
	result = {
		"name": "",
		"comment": outputComment,
	}
	if resultType is not None:
		resultSchema = {
			"title": "",
			"type": resultType,
		}
		if resultItems:
			resultSchema["items"] = resultItems
		result["schema"] = resultSchema
	if resultValues is not None:
		result["value"] = resultValues
	jsonMethod["result"] = result
	return jsonMethod


def convertSubsystem(handler, branch, outDir):
	handlerName = handler.attrib.get("name")
	if not handlerName:
		print("handler has no name")
		return

	branchDir = join(outDir, branch)
	os.makedirs(branchDir, exist_ok=True)

	# userDir = join(branch, "user")
	# adminDir = join(branch, "admin")
	# os.makedirs(userDir, exist_ok=True)
	# os.makedirs(adminDir, exist_ok=True)

	# userMethods = []
	# adminMethods = []
	methods = []
	for method in handler.getchildren():
		if method.tag != "method":
			continue
		authTypesStr = method.attrib.get("auth_type")
		if authTypesStr is None:
			print(f"no auth_type: {branch=}: {toStr(method)}")
			return
		if authTypesStr:
			authTypes = [x.strip() for x in authTypesStr.split(",")]
			for authType in authTypes:
				if authType not in ("ADMIN", "NORMAL_USER", "VOIP_USER", "ANONYMOUS"):
					print(f"bad auth_type={authType} in {authTypesStr!r}")
		else:
			authTypes = ["ADMIN", "NORMAL_USER", "VOIP_USER"]
		jsonMethod = getJsonMethod(handlerName, method, authTypes)
		if jsonMethod is None:
			continue

		methods.append(jsonMethod)
		# if "USER" in authTypes:
		# 	userMethods.append(jsonMethod)
		# if "ADMIN" in authTypes:
		# 	adminMethods.append(jsonMethod)

	with open(join(branchDir, handlerName + ".json"), "w") as _file:
		_file.write(dataToPrettyJson({
			"openrpc": "1.2.1",
			"info": {
				"version": "1.0.0",
				"title": f"IBSng: branch {branch}: USER: {handlerName}"
			},
			"methods": methods,
		}))
	# if userMethods:
	# 	with open(join(userDir, handlerName + ".json"), "w") as _file:
	# 		_file.write(dataToPrettyJson({
	# 			"openrpc": "1.2.1",
	# 			"info": {
	# 				"version": "1.0.0",
	# 				"title": f"IBSng: branch {branch}: USER: {handlerName}"
	# 			},
	# 			"methods": userMethods,
	# 		}))
	# if adminMethods:
	# 	with open(join(adminDir, handlerName + ".json"), "w") as _file:
	# 		_file.write(dataToPrettyJson({
	# 			"openrpc": "1.2.1",
	# 			"info": {
	# 				"version": "1.0.0",
	# 				"title": f"IBSng: branch {branch}: ADMIN: {handlerName}"
	# 			},
	# 			"methods": adminMethods,
	# 		}))



def convert(xmlFileName, branch, outDir):
	with open(xmlFileName, encoding="utf-8") as _file:
		doc = etree.XML(_file.read().encode("utf-8"))

	for handler in doc.getchildren():
		if handler.tag != "handler":
			continue
		convertSubsystem(handler, branch, outDir)


if __name__ == '__main__':
    fpath = sys.argv[1]
    branch = sys.argv[2]
    outDir = sys.argv[3]
    convert(fpath, branch, outDir)

"""
Splitting up the json into user/admin and subsystems/handlers, only adds %7 to the total size
	cat E/*/*.json | wc -l
		10090
	wc -l handlers_E.json 
		9365
"""

