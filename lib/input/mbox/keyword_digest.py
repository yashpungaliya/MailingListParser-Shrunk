import json
import mailbox

from analysis.author import ranking
import numpy as np
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer
from sklearn.feature_extraction.text import TfidfVectorizer

from analysis.author import ranking
from util import custom_stopwords
from util.read import *


def get_top_authors(top_n, json_filename):
    """
    Gets the top n authors based on the ranking generated from generate_author_ranking in analysis.author.ranking

    :param top_n: The number of top authors to be returned.
    :param json_filename: The JSON file from which author scores are generated.
    :return: Top authors and their indices
    """
    top_authors = set()
    top_authors_index = dict()
    author_scores = ranking.generate_author_ranking( json_filename, output_filename=None, active_score=2, passive_score=1, write_to_file=False)
    index = 0
    for email_addr, author_score in author_scores:
        index += 1
        top_authors.add(email_addr)
        top_authors_index[email_addr] = index
        if index == top_n:
            break
    return top_authors, top_authors_index


def save_sparse_csr(filename, array):
    """
    This function writes a numpy matrix to a file,given as a parameter, in a sparse format.

    :param filename: The file to store the matrix.
    :param array: The numpy array.
    """
    np.savez(filename,data = array.data ,indices=array.indices,
             indptr =array.indptr, shape=array.shape )


def get_message_body(message):
    """
    Gets the message body of the message passed as a parameter.

    :param message: The message whose body is to be extracted.
    :return: The message body from the message.
    """
    msg_body = None
    if message.is_multipart():
        for part in message.walk():
            if part.is_multipart():
                for subpart in part.walk():
                    msg_body = subpart.get_payload(decode=False)
            else:
                msg_body = part.get_payload(decode=False)
    else:
        msg_body = message.get_payload(decode=False)
    msg_body = msg_body.splitlines()
    for num in range(len(msg_body)):
        if msg_body[num]:
            if msg_body[num] == "---":
                msg_body = msg_body[:num]
                break
            if msg_body[num][0] == '>' or msg_body[num][0] == '+' or msg_body[num][0] == '-' or msg_body[num][0] == '@':
                msg_body[num] = ""
                if num > 0:
                    msg_body[num - 1] = ""
            elif msg_body[num][:3] == "Cc:":
                msg_body[num] = ""
            elif msg_body[num][:14] == "Signed-off-by:":
                msg_body[num] = ""
            elif msg_body[num][:9] == "Acked-by:":
                msg_body[num] = ""
            elif msg_body[num][:5] == "From:":
                msg_body[num] = ""
            elif msg_body[num][:10] == "Tested-by:":
                msg_body[num] = ""
            elif msg_body[num][:12] == "Reported-by:":
                msg_body[num] = ""
            elif msg_body[num][:12] == "Reviewed-by:":
                msg_body[num] = ""
            elif msg_body[num][:5] == "Link:":
                msg_body[num] = ""
            elif msg_body[num][:13] == "Suggested-by:":
                msg_body[num] = ""
    msg_body = [x.strip() for x in msg_body]
    msg_body = [x for x in msg_body if x != ""]
    msg_body = '\n'.join(msg_body)
    return msg_body


def generate_keyword_digest(mbox_filename, output_filename, author_uid_filename, json_filename, top_n = None, console_output=True):
    """
    From the .MBOX file, this function extracts the email content is extracted using two predefined classes
    available in the Python Standard Library: Mailbox and Message. Feature vectors are created for all the authors
    by obtaining meaningful words from the mail content, after removing the stop words, using NLTK libraries.
    The words obtained are transformed using stemming or lemmatization before adding these words to the word list of
    the corresponding authors. A matrix is created out of these word lists such that row set is the union of terms of
    all the authors and the column set contains the authors. If a term does not appear in a document, the corresponding
    matrix entry would be zero. The resulting matrix is called term-document matrix. Then tf-idf analysis is performed
    on the term-document matrix. Finally the top-10 words of each author is listed by their weight values.Each entry corresponds to the tf-idf normalized coefficient of the keyword for a user. If a keyword is not present
    in the top-10 keywords of a user, then the corresponding matrix entry would be zero. Also returns the feature names.

    :param mbox_filename: Contains the absolute or relative address of the MBOX file to be opened
    :return: Term Document Matrix: The columns of the matrix are the users and the rows of the matrix are the keywords.
    """
    english_stopwords = set(stopwords.words('english')) | custom_stopwords.common_words | custom_stopwords.custom_words
    email_re = re.compile(r'[\w\.-]+@[\w\.-]+')
    wnl = WordNetLemmatizer()

    print("Reading messages from MBOX file...")
    mailbox_obj = mailbox.mbox(mbox_filename)
    with open(author_uid_filename, 'r') as map_file:
        author_uid_map = json.load(map_file)
        map_file.close()

    if top_n is None:
        print("Reading author UIDs from JSON file...")
        keywords_list = [list() for x in range(max(author_uid_map.values())+1)]
    else:
        top_n = min(len(author_uid_map), top_n)
        top_authors, top_authors_index = get_top_authors(top_n, json_filename)
        keywords_list = [list() for x in range(top_n+1)]

    i = 0 # Number of emails processed
    with open(output_filename, 'w') as out_file:
        for message in mailbox_obj:
            temp = email_re.search(str(message['From']))
            from_addr = temp.group(0) if temp is not None else message['From']
            if top_n is not None and from_addr not in top_authors:
                continue
            if top_n is None and from_addr not in author_uid_map.keys():
                continue

            msg_body = get_message_body(message)
            if from_addr is None:
                from_addr = message['From']
            msg_tokens = [x.lower() for x in re.sub('\W+', ' ', msg_body).split() if 2 < len(x) < 30]
            # Toggle comment below if numbers and underscores should also be removed.
            # msg_tokens = [x for x in re.sub('[^a-zA-Z]+', ' ', msg_body).split() if 2 < len(x) < 30]

            msg_tokens = [wnl.lemmatize(x) for x in msg_tokens if not x.isdigit() and x not in from_addr]
            msg_tokens = [x for x in msg_tokens if x not in english_stopwords]

            if top_n is None:
                keywords_list[author_uid_map[from_addr]].extend(msg_tokens)
            else:
                keywords_list[top_authors_index[from_addr]].extend(msg_tokens)

            if not console_output:
                i += 1
                if not i % 10000:
                    print(i, "of", len(mailbox_obj), "messages processed.")

        for num in range(len(keywords_list)):
            keywords_list[num] = " ".join(keywords_list[num])

        print("Performing tf-idf analysis on the term-document matrix...")
        vectorizer = TfidfVectorizer(analyzer='word', stop_words=english_stopwords, max_df=0.9, min_df=0.05,
                                     use_idf=True, ngram_range=(1, 4))
        tfidf_matrix = vectorizer.fit_transform(keywords_list).toarray()
        feature_names = vectorizer.get_feature_names()
        if top_n is None:
            for author_email, author_uid in author_uid_map.items():
                if max(tfidf_matrix[author_uid]) > 0 and len(keywords_list[num]) > 99:
                    try:
                        indices = tfidf_matrix[author_uid].argsort()[-20:][::-1]
                        if not console_output:
                            out_file.write(author_email + "\n")
                            author_features = list()
                            for i in indices:
                                author_features.append(feature_names[i])
                                # author_features.append((feature_names[i], tfidf_matrix[author_uid][i]))
                            author_features.sort(key=lambda x: -1*len(x))
                            for i2 in range(len(author_features)):
                                overlap_flag = 0
                                for i1 in range(i2+1, len(author_features)):
                                    if author_features[i1] in author_features[i2]:
                                        overlap_flag = 1
                                        break
                                if not overlap_flag:
                                    out_file.write(author_features[i2] + ", ")
                        else:
                            print("ERROR: Console Output not implemented! Please write to file.")

                    except:
                        pass
                    finally:
                        if console_output:
                            print("\n-----\n")
                        else:
                            out_file.write("\n-----\n")
        else:
            term_document_matrix = np.zeros((len(feature_names), top_n), dtype=float)
            for author_email, author_uid in top_authors_index.items():
                if max(tfidf_matrix[author_uid]) > 0 and len(keywords_list[author_uid]) > 99:
                    try:
                        indices = tfidf_matrix[author_uid].argsort()[-20:][::-1]
                        if not console_output:
                            out_file.write(author_email + "\n")
                            author_features = list()
                            for i in indices:
                                author_features.append(feature_names[i])
                                # author_features.append((feature_names[i], tfidf_matrix[author_uid][i]))
                            author_features.sort(key=lambda x: -1 * len(x))
                            for i2 in range(len(author_features)):
                                overlap_flag = 0
                                for i1 in range(i2+1, len(author_features)):
                                    if author_features[i1] in author_features[i2]:
                                        overlap_flag = 1
                                        break
                                if not overlap_flag:
                                    out_file.write(author_features[i2]+", ")
                        else:
                            print("ERROR: Console Output not implemented! Please write to file.")
                    except:
                        pass
                    finally:
                        if console_output:
                            print("\n-----\n")
                        else:
                            out_file.write("\n-----\n")
            # with open("author_top_index.json", 'w') as json_file:
            #     json.dump(top_authors_index, json_file)
            # print(feature_names)

        return top_authors_index, term_document_matrix, feature_names

    # generate_keyword_digest("lkml.mbox")
