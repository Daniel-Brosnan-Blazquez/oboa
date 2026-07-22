# OBOA

# OBOA requirements

OBOA stands for Orchestrator for Business Operations Analysis.

The following represents the requirements to be covered by OBOA

1. OBOA shall poll an input directory to orchestrate the files included inside  
2. OBOA shall make use of ABOA to archive the orchestrated files, which is the default orchestration flow  
3. OBOA shall have a database inventory  
4. The database inventory will be based on Postgres  
5. The design of the data model will be done in pgmodeler  
6. The database inventory shall include the following tables:  
   1. orchestration\_configurations  
   2. orchestrated\_files  
   3. orchestration\_operations  
7. The orchestrated\_files table shall include the following metadata:  
   1. file\_uuid  
   2. name  
   3. path  
   4. group  
   5. reception date  
   6. archived  
   7. processed  
   8. orchestrator\_configuration  
8. The orchestration\_configurations table shall include the following metadata:  
   1. path  
   2. active\_from  
   3. active\_until  
   4. active  
   5. content  
9. The orchestration\_operations table shall include the following metadata:  
   1. operation  
   2. time\_stamp  
   3. status  
   4. message  
   5. file\_uuid  
10. OBOA shall provide the following APIs:  
    1. Command line API  
11. OBOA shall provide an API to configure the management of data (files) through an XML with the following structure:  
    1. \<orchestrator\_configuration\>  
    2. \<data group=”” priority=””\>  
    3. \<data\_mask\>\</data\_mask\>  
    4. \<data\_processor\>\</data\_processor\>  
    5. \</data\>  
    6. \</orchestrator\_configuration\>  
    7.   
    8. Where:  
       1. data\_processor is optional  
       2. priority is a number from 1 onwards, 1 being the highest priority  
12. OBOA shall evaluate the structure of the configuration using an XSD schema  
13. OBOA shall orchestrate a file even if the file is not matching any configuration assigning “unknown” group  
14. OBOA shall not accept any configuration which defines group with the value “unknown”  
15. OBOA shall expect data processors declared in the configuration to be executable scripts  
16. OBOA shall have tests covering all the code of the component  
17. OBOA shall follow the code structure of the ABOA component  
18. Engine should have the following additional configuration parameters:  
    1. polling\_dir  
    2. polling\_frequency  
19. OBOA shall have an option to delete the files from the input folder after archiving. However, if the file matches an orchestration rule with a data processor configured, the file is hard-linked or copied to another internal folder for further processing.  
20. The internal folder for further processing shall be configurable.  
21. OBOA shall run as a daemon.  
