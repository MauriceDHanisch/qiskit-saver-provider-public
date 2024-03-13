from typing import Optional, List, Dict, Any
import warnings
import re

import numpy as np
import matplotlib.pyplot as plt

from qiskit.providers import JobV1
from qiskit.providers.backend import Backend
from qiskit.result import Result

class SavedJob(JobV1):
    def __init__(
        self,
        backend: Backend | None,
        job_id: str,
        tags: Optional[List[str]] = None,
        name: Optional[str] = None,
        backend_options: Dict[str, Any] = None,
        initial_layouts: Optional[List[Dict[str, str]]] = None,  
        final_layouts: Optional[List[Dict[str, str]]] = None,    
        **kwargs,
    ) -> None:
        self._tags = tags
        self._name = name
        self._result = None
        self._creation_date = kwargs.pop("creation_date", None)
        self._backend_options = backend_options
        self._initial_layouts = initial_layouts  
        self._final_layouts = final_layouts      
        super().__init__(backend, job_id, **kwargs)

    def set_result(self, result: Result):
        self._result = result

    def creation_date(self):
        return self._creation_date

    def result(self, *args, **kwargs):
        return self._result

    def backend_options(self):
        return self._backend_options
    
    def initial_layouts(self):
        return self._initial_layouts
    
    def final_layouts(self):
        return self._final_layouts

    @classmethod
    def from_job(cls, job: JobV1) -> "SavedJob":
        if hasattr(job, "tags"):
            tags = job.tags()
        else:
            tags = None
        if hasattr(job, "name"):
            name = job.name()
        else:
            name = None
        if hasattr(job, "creation_date"):
            creation_date = job.creation_date()
        else:
            creation_date = None
        if hasattr(job, "backend_options"):
            backend_options = job.backend_options()
        else:
            backend_options = None

        initial_layouts = [cls.serialize_layout(circ.layout.initial_layout) for circ in job.circuits()]
        final_layouts = [cls.serialize_layout(circ.layout.final_layout) for circ in job.circuits()]
        
        new_job: "SavedJob"
        new_job = cls(
            job.backend(),
            job.job_id(),
            tags=tags,
            name=name,
            creation_date=creation_date,
            backend_options=backend_options,
            initial_layouts=initial_layouts,
            final_layouts=final_layouts,
            **job.metadata,
        )
        new_job.set_result(job.result())
        return new_job

    @staticmethod
    def serialize_layout(layout):
        if layout is None:
            return None
        return {str(qubit): str(layout[qubit]) for qubit in layout.get_virtual_bits()}
    
    @staticmethod
    def deserialize_layout(serialized_layout_dict: Dict[str, str]):
        ''' Deserialize the layout dictionary to a dictionary of QuantumRegisters and qubit indices.

        Returns:
            dict: e.g. {'ancilla': {0: 0, 1: 1}, 'code': {0: 2, 1: 3}}
        
        '''
        # Initialize a dictionary to hold the parsed data
        parsed_registers = {}
        
        # Define a regex pattern to extract the register name and qubit index
        pattern = r"QuantumRegister\(\d+, '(\w+)'\), (\d+)"
        
        # Iterate over each item in the serialized dictionary
        for qubit_str, physical_qubit_str in serialized_layout_dict.items():
            # Use regex to find matches in the string
            match = re.search(pattern, qubit_str)
            if match:
                register_name = match.group(1)  # Extract the register name
                qubit_index = int(match.group(2))  # Extract the qubit index as an integer
                physical_qubit = int(physical_qubit_str)  # Convert physical qubit location to integer
                
                # If the register name doesn't exist in the dictionary, add it
                if register_name not in parsed_registers:
                    parsed_registers[register_name] = {}
                
                # Map the qubit index to the physical qubit for the register
                parsed_registers[register_name][qubit_index] = physical_qubit

        for register_name in parsed_registers:
            parsed_registers[register_name] = {k: v for k, v in sorted(parsed_registers[register_name].items())}
            
        return parsed_registers

    def submit(self):
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support submitting jobs."
        )

    def status(self):
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support checking the status."
        )

    def tags(self):
        return self._tags

    def name(self):
        return self._name
