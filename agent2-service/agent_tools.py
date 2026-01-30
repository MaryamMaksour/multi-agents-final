
from __future__ import annotations

from .tools import get_table_records, db_execute, embed_query_tool, get_filter, get_table_schema
 
tools = [get_table_records,db_execute, embed_query_tool, get_table_schema, get_filter]
tools_dict = {tool.name: tool for tool in tools} # Creating a dictionary of our tools

def get_tools():
   return tools

def get_tools_dict():
   return tools_dict


