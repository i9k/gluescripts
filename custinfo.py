from pyspark.sql.types import *
from pyspark.sql import SparkSession
from pyspark.sql.functions import *
import re
import os
import json
import builtins

# get useful files for gender detection
name_db, title_db, hypoc_db, grammg_db = [json.load(open(f,'r')) for f in [os.path.join(os.path.dirname(__file__),'data/data_names_.json'), 
																	 		   os.path.join(os.path.dirname(__file__),'data/data_salutations_.json'), 
																	 		   os.path.join(os.path.dirname(__file__),'data/data_hypocorisms_.json'),
																	 		   os.path.join(os.path.dirname(__file__),'data/data_grammgender_.json')]]

def getGenderTitle(s):
	"""
	string s is presumably a title
	"""
	for g in 'm f'.split():
		if s and (s.lower() in title_db['common'][g] + title_db['uncommon'][g]):
				return g

def getGenderName(s):
	"""
	s is a string possibly containing name
	"""
	if not s:
		return None

	# any name found straight away or hypocorisms? hypoc_db has hypocs as keys
	nameparts_incommon = {_ for w in s.split() for _ in w.split('-')} & (set(name_db) | set(hypoc_db))

	if nameparts_incommon:

		name_cand = builtins.max(nameparts_incommon, key=len)

		# if candidate is name (and not hypoc)
		if name_cand in name_db:
			return name_db[name_cand]
		else:
			# find what names corresp.to hypocorism and are in the name database
			unfolded_hypoc = set(hypoc_db[name_cand]) & set(name_db)

			if unfolded_hypoc:
				hyp_cand = builtins.max(unfolded_hypoc, key=len)
				return name_db[hyp_cand]

def getDomain(s):

	# given a string s, extract the domain part if this string happens to be an email

	if not isinstance(s, str):
		return ''

	return s.strip().split('@')[-1]


def isStudentOrStaff(s):

	# given a string s and if it's an email address, is it a university student or staff?

	staffPattern = re.compile(r"\b[a-z-]+\.*[a-z-]+\@[a-z]+\.?edu\.*(au)*\b")
	studentPattern = re.compile(r"\b\d*\w+\d+\w*\@[a-z]+\.?edu\.*(au)*\b")

	staff_match = re.match(staffPattern, s)
	student_match = re.match(studentPattern, s)

	sos = "no"

	if staff_match:
		sos = "staff"

	if student_match:
		sos = "student"

	return sos


def isUni(s):

	# given a string s, figure out which university exactly it's from (if any)

	p = getDomain(s)

	unis = {
		"adelaide.edu.au" : "university of adelaide",
		"acu.edu.au" : "australian catholic university",
		"anu.edu.au" : "australian national university",
		"bond.edu.au" : "bond university",
		"canberra.edu.au" : "university of canberra",
		"cqu.edu.au" : "cquniversity",
		"cdu.edu.au" : "charles darwin university",
		"csu.edu.au" : "charles sturt university",
		"curtin.edu.au" : "curtin university",
		"deakin.edu.au" : "deakin university",
		"ecu.edu.au" : "edith cowan university",
		"federation.edu.au" : "federation university",
		"flinders.edu.au" : "flinders university",
		"griffith.edu.au" : "griffith university",
		"jcu.edu.au" : "james cook university",
		"latrobe.edu.au" : "la trobe university",
		"mq.edu.au" : "macquarie university",
		"unimelb.edu.au" : "university of melbourne",
		"monash.edu" : "monash university",
		"murdoch.edu.au" : "murdoch university",
		"une.edu.au" : "university of new england",
		"unsw.edu.au" : "university of new south wales",
		"newcastle.edu.au" : "university of newcastle",
		"nd.edu.au" : "university of notre dame",
		"uq.edu.au" : "university of queensland",
		"qut.edu.au" : "qut",
		"rmit.edu.au" : "rmit",
		"unisa.edu.au" : "university of south australia",
		"scu.edu.au" : "southern cross university",
		"usq.edu.au" : "university of southern queensland",
		"usc.edu.au" : "usc",
		"swin.edu.au" : "swinburne university",
		"sydney.edu.au" : "university of sydney",
		"utas.edu.au" : "university of tasmania",
		"uts.edu.au" : "university of technology sydney",
		"vu.edu.au" : "victoria university",
		"uwa.edu.au" : "university of western australia",
		"westernsydney.edu.au" : "western sydney university",
		"uow.edu.au" : "university of wollongong"
		}

	return unis.get(p, "none")

getGenderTitleUDF = udf(getGenderTitle, StringType())

getGenderNameUDF = udf(getGenderName, StringType())

isUniUDF = udf(isUni, StringType())

isStudentOrStaffUDF = udf(isStudentOrStaff, StringType())

# in pyspark Spark session is readily available as spark
spark = SparkSession.builder.master("local").appName("test session").getOrCreate()

# set a smaller number of executors because this is running locally
spark.conf.set("spark.sql.shuffle.partitions", "4")

df = spark.read.option("inferSchema", "true").option("header", "true").csv("data/sample_LotusCustomer.csv.gz")

df1 = df.filter(df.CustomerID.isNotNull()) \
		.filter(df.CustomerListID == 2) \
		.filter(~df.EmailAddress.contains("ticketek"))

df2 = df1.withColumn("EmailAddress_", \
					when(df1.EmailAddress.contains("@"), lower(df1.EmailAddress)).otherwise(""))

df3 = df2.withColumn("University", isUniUDF(df2.EmailAddress_)) \
		.withColumn("isStudentOrStaff", isStudentOrStaffUDF(df2.EmailAddress_)) \
		.withColumn("Postcode", regexp_extract(df2.Postcode,"\\b(([2-8]\\d{3})|([8-9]\\d{2}))\\b",0)) \
		.withColumn("Salutation", when(lower(regexp_replace(df2.Salutation,"[^A-Za-z]","")) \
										.isin(["mr","ms","mrs","dr","mister","miss"]), lower(df.Salutation)) \
										.otherwise("")) \
		.withColumn("DateOfBirth", when(year(df2.DateOfBirth) < 1918, lit(None)).otherwise(df2.DateOfBirth)) \
		.withColumn("FirstName", ltrim(lower(regexp_replace(df2.FirstName, "[-]"," ")))) \
		.withColumn("LastName", ltrim(lower(regexp_replace(regexp_replace(df2.LastName,"['`]",""),"[-]"," ")))) \
		.withColumn("MobilePhone", regexp_extract(regexp_replace(df2.MobilePhone,"\\s",""),"(\\+*(?:61)*|0*)(4\\d{8})",2)) \
		.withColumn("State", lower(df2.State)) \
		.withColumn("City", lower(df2.City)) \
		.withColumn("CountryName", lower(df2.CountryName))

df4 = df3.withColumn("Gender", getGenderNameUDF(df3.FirstName)) \
		.select("CustomerID", "Salutation", "Gender", "FirstName", "LastName", "DateOfBirth", 
					"CreatedDate", "ModifiedDate", "EmailAddress","University", "isStudentOrStaff", "State", "City","Postcode",
							"CountryName","MobilePhone", "HomePhone", "WorkPhone") \
		.repartition(1) \
		.write.option("header","true").mode("overwrite").option("compression", "gzip").csv("out")