from application.conversion.parser import main as parser
from application.database import get_db
from flask import Blueprint, request, current_app, jsonify, json, g, make_response
from flask_cors import CORS, cross_origin

import os
import redis
from rq import Queue, Connection
import hashlib
import time
import json
import logging
from datetime import datetime
from application.redis_worker import get_worker_pipeline
from application.redis_connection import get_redis_connection

documents = Blueprint("documents", __name__,
                        template_folder="templates")

def genHash(content=""):
    """Generate hash value of given input string data

    Please specify MD5 / SHA-256.
    Based on Python standard library hashlib

    :param content: string type data to be input for hashing (default "")
    :returns: m.hexdigest()
    :rtype: string
    """
    # Generate Hash
    # m = hashlib.sha256()
    m = hashlib.md5()
    m.update(content.encode("utf-8"))
    return m.hexdigest()

def queue_convert_doc(res={}, processed_content="", hash_id="", user_id="", filename="", filepath=""):
    """Add submission to task list in database, and ready to be queue for
    further processing.
    
    :param res: dict object which is built to produce Flask.Response() (default {})
    :param processed_content: string type data to be input for hashing (default "")
    :param hash_id: (default "")
    :param user_id: (default "")
    :param filename: (default "")
    :param filepath: (default "")

    :returns: JSON
    :rtype: Flask.Response()
    """
    cursor = None
    cur = None
    job_id = ""
    insertID = ""
    result = {}

    # 1. New entry in table `document`, record the status of a) conversion file or b) process_analysis
    with current_app.app_context():
        try:
            # MySQL
            db = get_db()
            conn = db.connect()
            cursor = conn.cursor()

            process_stage = "UPLOADED"

            if filename == "" and filepath == "":
                # Text
                cursor.execute("INSERT INTO document (body, uuid, process_stage) VALUES (%s, %s, %s);", (processed_content, hash_id, process_stage))
            else:
                # File
                cursor.execute("INSERT INTO document (body, uuid, process_stage, file_name, filepath) VALUES (%s, %s, %s, %s, %s);", ("", hash_id, process_stage, filename, filepath))

            conn.commit()
            insertID = cursor.lastrowid

        except Exception as e:
            # Response with failure in case of any exception
            res["status"] = "FAILED"
            res["msg"] = f"Cannot insert DB.\n{e}"
            res["result"] = []
            logging.warn(f"Cannot insert DB.\n{e}")

        else:
            # After successful insertion, process the text and response with the document ID.
            result["id"] = insertID
            result["uuid"] = hash_id
            res["status"] = "OK"
            res["msg"] = f"Record inserted."

            try:
                redis_connection = get_redis_connection()
                logging.warn("current_app.config: " + str(current_app.config["QUEUES"]))
                q = Queue(current_app.config["QUEUES"][1], connection=redis_connection)
                job = {}

                if filename == "" and filepath == "":
                    # Text
                    job = q.enqueue(process_analysis, str(insertID), hash_id)
                else:
                    # File
                    job = q.enqueue(process_convert, str(insertID), hash_id, filename, filepath)

                job_id = job.get_id()
                result["task_id"] = job_id

                logging.warn("Processing queued with job ID: " + str(job_id))
                logging.warn(f"Current {current_app.config['QUEUES'][1]} Queue: " + str(len(q)))
            except Exception as e:
                logging.warn(f"Queue failed\n{e}")

        finally:
            # MySQL
            if cursor is not None:
                cursor.close()

        # Default return
        res["result"] = [result]
        return make_response(jsonify(res))

############
# Image Extract
# yourapp
def process_convert(id, uuid, filename="", filepath=""):
    """Fetch a task in task list, do conversion of the content.

    It write output results to text files on local disk.
    Update task status in database after task is finished.
    
    :param id: database auto incremental id
    :param uuid: unique id of database
    :param filename: (default "")
    :param filepath: (default "")

    :returns: success
    :rtype: boolean
    """
    cur = None
    db = None
    with current_app.app_context():
        try:
            logging.warn("Processing document {}.".format(id))

            # MySQL
            db = get_db()
            conn = db.connect()
            cursor = conn.cursor()

            cursor.execute("SELECT process_status, body FROM document WHERE uuid = %s;", (uuid))
            result = cursor.fetchall()
            body = result[0][1]

            if True or len(body) > 0:

                if False and body["process_status"] == "FINISHED":
                    logging.warn("document {} already processed.".format(uuid))
                    success = True
                else:
                    # MySQL
                    cursor.execute("UPDATE document SET process_status = 'PROCESSING_CONVERT' WHERE uuid = %s;", (uuid))
                    conn.commit()

                    result = ""
                    try:
                        # result = parser(
                        #     filename=filename,
                        #     filepath=filepath,
                        #     newname=filename+"_converted",
                        # )
                        from yourapp.main import main
                        # return paths of Images files
                        result = main(
                            id=id,
                            uuid=uuid,
                            filename=filename,
                            filepath=filepath,
                        )
                    except Exception as e:
                        with open("/home/flask/app/output_files/{}-{}.txt".format(id, uuid), mode="a", encoding="utf8") as f:
                            f.write("Error in main: {}".format(e))

                    # MySQL
                    cursor.execute("UPDATE document SET process_status = 'FINISHED', processed_body = %s WHERE uuid = %s;", (json.dumps(result), uuid))
                    conn.commit()
                    success = True

                    insertID = id

                    """
                    No need text analysis
                    """
                    # try:
                    #     redis_connection = get_redis_connection()
                    #     q = Queue(current_app.config['QUEUES'][0], connection=redis_connection)
                    #     job = q.enqueue(process_analysis, str(insertID), uuid, submission_id)
                    #     job_id = job.get_id()
                    #     logging.warn("text processing queued with job ID: " + str(job_id))
                    #     logging.warn(f"Curr {current_app.config['QUEUES'][0]} Queue: " + str(len(q)))
                    # except Exception as e:
                    #     logging.warn(f"queue failed, process text in local thread\n{e}")
                    #     # process_success = process_analysis(insertID)
                    #     # if(not process_success["status"]):
                    #     #     res["success"] = False

            else:
                print("unable to get document {} .".format(id))
                success = False
        except Exception as e:
            pass
            with open("/home/flask/app/output_files/{}-{}.txt".format(id, uuid), mode="a", encoding="utf8") as f:
                f.write("\n")
                f.write(str(e))
            success = False
        finally:
            pass
        return success

# SKIPPED: backend method to process a single text
def process_analysis(id, uuid, submission_id=""):
    """Fetch a task in task list, do analysis of the content.

    It write output results to text files on local disk.
    Update task status in database after task is finished.
    
    :param id:
    :param uuid:
    :param submission_id:

    :returns: success
    :rtype: boolean
    """

    # No more text processing is needed.
    success = True
    return success
    pass


    """
    cur = None
    db = None
    with open("/home/flask/app/output_files/{}-{}.txt".format(id, uuid), mode="a", encoding="utf8") as f:
        f.write("test in main: {}===>OK 1".format(id))
    with current_app.app_context():
        try:
            logging.warn("processing document {}.".format(id))

            # MySQL
            db = get_db()
            conn = db.connect()
            cursor = conn.cursor()
            cursor.execute("SELECT process_status, processed_body, submission_id FROM document WHERE uuid = %s;", (uuid))
            result = cursor.fetchall()
            body = result[0][1]

            if True or len(body) > 0:

                if False and body["process_status"] == "FINISHED":
                    logging.warn("document {} already processed.".format(id))
                    success = True
                else:
                    # MySQL
                    cursor.execute("UPDATE document SET process_status = 'PROCESSING' WHERE uuid = %s;", (uuid))
                    conn.commit()

                    result = {}
                    # Import yourapp
                    from yourapp.main import main
                    try:
                        result = main(
                            id=id,
                            uuid=uuid,
                            body=body,
                        )
                    except Exception as e:
                        with open("/home/flask/app/output_files/{}-{}.txt".format(id, uuid), mode="a", encoding="utf8") as f:
                            f.write("Error in main: {}".format(e))

                    with open("/home/flask/app/output_files/{}-{}.txt".format(id, uuid), mode="a", encoding="utf8") as f:
                        f.write("\n\ntest in main: {}===>OK 3".format(json.dumps(result)))

                    try:
                        # MySQL
                        cursor.execute("UPDATE document SET process_status = 'FINISHED', processed_body = %s WHERE uuid = %s;", (json.dumps(result), uuid))
                        process_status = "FINISHED"
                        length_by_sentence = result["processed_body"]["length_by_sentence"]
                        length_by_distinct_token = result["processed_body"]["length_by_distinct_token"]
                        length_by_word = result["processed_body"]["length_by_word"]
                        length_by_character = result["processed_body"]["length_by_character"]
                        lexical_diversity = result["processed_body"]["lexical_diversity"]
                        data_by_sentence = result["processed_body"]["data_by_sentence"]
                        data_by_fdist = result["processed_body"]["data_by_fdist"]
                        wordfrequency_all = result["processed_body"]["wordfrequency_all"]
                        wordfrequency_content = result["processed_body"]["wordfrequency_content"]
                        wordfrequency_function = result["processed_body"]["wordfrequency_function"]
                        wordrangescore = result["processed_body"]["wordrangescore"]
                        academicwordscore = result["processed_body"]["academicwordscore"]
                        academic_sublists_score = result["processed_body"]["academic_sublists_score"]
                        familiarityscore = result["processed_body"]["familiarityscore"]
                        concretenessscore = result["processed_body"]["concretenessscore"]
                        imagabilityscore = result["processed_body"]["imagabilityscore"]
                        meaningfulnesscscore = result["processed_body"]["meaningfulnesscscore"]
                        meaningfulnesspscore = result["processed_body"]["meaningfulnesspscore"]
                        ageofacquisitionscore = result["processed_body"]["ageofacquisitionscore"]
                        grammar_errorrate = result["processed_body"]["grammar_errorrate"]
                        flesch_reading_ease = result["processed_body"]["flesch_reading_ease"]
                        flesch_kincaid_grade_level = result["processed_body"]["flesch_kincaid_grade_level"]
                        smog = result["processed_body"]["smog"]
                        coleman_liau = result["processed_body"]["coleman_liau"]
                        ari = result["processed_body"]["ari"]
                        semanticoverlap = result["processed_body"]["semanticoverlap"]
                        typetokenratio = result["processed_body"]["typetokenratio"]
                        holistic_score = result["processed_body"]["holistic_score"]
                        cursor.execute("INSERT INTO tbl_submit_document_stat (submission_id, uuid, process_status, length_by_sentence, length_by_distinct_token, length_by_word, length_by_character, lexical_diversity, data_by_sentence, data_by_fdist, wordfrequency_all, wordfrequency_content, wordfrequency_function, wordrangescore, academicwordscore, academic_sublists_score, familiarityscore, concretenessscore, imagabilityscore, meaningfulnesscscore, meaningfulnesspscore, ageofacquisitionscore, grammar_errorrate, flesch_reading_ease, flesch_kincaid_grade_level, smog, coleman_liau, ari, semanticoverlap, typetokenratio, holistic_score) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);", (
                            submission_id,
                            uuid,
                            process_status,
                            length_by_sentence,
                            length_by_distinct_token,
                            length_by_word,
                            length_by_character,
                            lexical_diversity,
                            data_by_sentence,
                            data_by_fdist,
                            wordfrequency_all,
                            wordfrequency_content,
                            wordfrequency_function,
                            wordrangescore,
                            academicwordscore,
                            academic_sublists_score,
                            familiarityscore,
                            concretenessscore,
                            imagabilityscore,
                            meaningfulnesscscore,
                            meaningfulnesspscore,
                            ageofacquisitionscore,
                            grammar_errorrate,
                            flesch_reading_ease,
                            flesch_kincaid_grade_level,
                            smog,
                            coleman_liau,
                            ari,
                            semanticoverlap,
                            typetokenratio,
                            holistic_score,
                        ))
                        conn.commit()
                        success = True
                    except Exception as e:
                        with open("/home/flask/app/output_files/{}-{}.txt".format(id, uuid), mode="a", encoding="utf8") as f:
                            f.write("\n\ntest in main: {}===>Error DB".format(e))
            else:
                print("unable to get document {} .".format(id))
                success = False
        except Exception as e:
            with open("/home/flask/app/output_files/{}-{}.txt".format(id, uuid), mode="a", encoding="utf8") as f:
                f.write("\n")
                f.write(str(e))
            success = False
        finally:
            with open("/home/flask/app/output_files/{}-{}.txt".format(id, uuid), mode="a", encoding="utf8") as f:
                f.write("\n\ntest in main: {}===>OK Finally".format(""))
            pass
        return success
        """

# For testing of the queue_convert_doc function
@documents.route('/', methods = ["GET", "POST"])
def testing():
    req = request.get_json()
    res = main(
        uid="1",
        body="demo",
    )
    return jsonify({"success":json.loads(res)})

# Tasks Status
@documents.route('/status', methods = ["GET"])
@cross_origin()
def get_status():
    req = request.get_json()
    res = {
        "error": "Some error on /status"
    }

    atype = "all"
    page = "0"
    limit = "10"
    if request.method == 'GET':
        atype = request.args.get('type', default="all")
        page = request.args.get('page', default="0")
        limit = request.args.get('limit', default="10")

    wanted_fields = [
        "uuid",
        "process_stage",
        "process_status",
        "body",
        "processed_body",
        "file_name",
        "filepath"
    ]

    afilter = {
        "all": ["PROCESSING_CONVERT", "FINISHED", "PROCESSING", "NOT PROCESSED"],
        "finished": ["FINISHED", "<FILLER>"],
        "unfinished": ["PROCESSING_CONVERT", "PROCESSING", "NOT PROCESSED"],
    }

    # MySQL
    db = get_db()
    conn = db.connect()
    cursor = conn.cursor()

    try:
        page = int(page)
        limit = int(limit)
    except:
        page = 0
        limit = 10
        logging.warn(f"[WARN] get_status: convert page or limit failed: {page}, {limit}. Use default (page 0, limit 10)")

    cursor.execute("SELECT {} FROM document WHERE process_status in {} LIMIT %s OFFSET %s;".format(
        ", ".join(wanted_fields),
        str(tuple(afilter[atype])),
    ), (limit, page * limit))
    result = cursor.fetchall()

    dict_result = [dict(zip(wanted_fields, row)) for row in result]

    return jsonify({
        "status": "OK",
        "msg": "OK",
        "result": dict_result,
    })

# Queue Status
@documents.route('/queue', methods = ["GET"])
@cross_origin()
def get_queue_status():
    req = request.get_json()
    res = {
        "error": "Some error on /status"
    }

    with current_app.app_context():
        redis_connection = get_redis_connection()
        q = Queue(current_app.config['QUEUES'][1], connection=redis_connection)
        queued_job_ids = q.job_ids
        res = {
            "queue": queued_job_ids,
            "len": len(q),
        }
    return jsonify({
        "status": "OK",
        "success": res
    })

# Get a document
@documents.route('/get', methods = ["GET", "POST"])
@cross_origin()
def get_doc():
    id = ""
    uuid = ""
    if request.method == 'GET':
        uuid = request.args.get('uuid')

    req = request.get_json()
    res = {
        "error": "Some error on /status"
    }

    if req:
        id = req['submission_id']
        if 'uuid' in req.keys():
            uuid = req['uuid']

    wanted_fields = [
        "uuid",
        "process_stage",
        "process_status",
        "body",
        "processed_body",
        "file_name",
        "filepath"
    ]

    # MySQL
    db = get_db()
    conn = db.connect()
    cursor = conn.cursor()

    cursor.execute("SELECT {} FROM document WHERE uuid = %s;".format(", ".join(wanted_fields)), (uuid))
    result = cursor.fetchall()

    if len(result) == 0:
        # Record not exist
        return jsonify({
            "status": "FAILED",
            "msg": "No result.",
            "result": [],
        })
    else:
        logging.warn(result[0])
        if result[0][wanted_fields.index("process_status")] != "FINISHED":
            # still waiting for processing
            return jsonify({
                "status": "OK",
                "msg": "Processing.",
                "result": [],
            })
        else:
            #body = result[0]
            cursor = conn.cursor()
            cursor.execute("SELECT {} FROM document WHERE uuid = %s;".format(", ".join(wanted_fields)), (uuid))
            result2 = cursor.fetchall()

            dict_result = [dict(zip(wanted_fields, row)) for row in result2]

            return jsonify({
                "status": "OK",
                "msg": "OK",
                "result": dict_result,
            })

@documents.route('/new', methods = ["POST", "GET"])
@cross_origin()
def new_file():
    req = request.get_json()
    res = {}
    res["success"] = False

    if request.method == 'POST':
        user_id = request.form.get('user_id')

        if 'file' not in request.files:
            print('No file attached in request')
            # Try text:
            inputContent = request.form.get('textline')
            inputContent = inputContent.strip()

            # No text either:
            if inputContent == '' or len(submission_id) == 0:
                print('No text in request')
                return make_response(jsonify({
                    'status': 'FAILED',
                    'msg': 'No text in in request or no submission_id'
                }), 502)

            # Prepare to Queue Conversion
            processed_content = inputContent
            hash_id = genHash(processed_content)
            return queue_convert_doc(res, processed_content, hash_id, user_id)

        # Trying File:
        file0 = request.files['file']
        if file0.filename == '':
            print('No file selected')
            return make_response(jsonify({
                'status': 'FAILED',
                'msg': 'No file selected'
            }), 502)

        if file0:
            filename = file0.filename
            filepath = ""
            try:
                filepath = os.path.join('/home/flask/app/output_files/', filename)
                file0.save(filepath)
            except Exception as e:
                logging.warn(f'write file error: \n{e}')

            # # Prepare to Queue Conversion
            # processed_content = inputContent
            # hash_id = genHash(processed_content)
            now = datetime.now()
            timestamp = datetime.timestamp(now)
            hash_id = genHash(f'{filename}_{timestamp}')
            return queue_convert_doc(res, "", hash_id, user_id, filename=filename, filepath=filepath)

    # Not a POST request
    return make_response(jsonify({
        'status': 'FAILED',
        'msg': 'POST method is preferred.'
    }), 502)
