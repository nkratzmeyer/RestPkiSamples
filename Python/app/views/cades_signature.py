import os
import uuid
from flask import make_response, render_template, request
from lacunarestpki import CadesSignatureStarter, StandardSignaturePolicies, \
    CadesSignatureFinisher

from app import APPDATA_FOLDER, STATIC_FOLDER
from app.blueprints import cades_signature
from app.util import get_restpki_client, get_expired_page_headers, \
    get_security_context_id


@cades_signature.route('/')
@cades_signature.route('/<userfile>')
@cades_signature.route('/cosign/<cmsfile>')
def index(userfile=None, cmsfile=None):
    """

    This function initiates a CAdES signature using REST PKI and renders the
    signature page.

    All CAdES signature examples converge to this action, but with different
    URL arguments:

        1. Signature with a server file               : no arguments filled
        2. Signature with a file uploaded by the user : "userfile" filled
        3. Co-signature of a previously signed CMS    : "cmsfile" filled

    """

    try:

        # Get an instantiate of the CadesSignatureStarter class, responsible for
        # receiving the signature elements and start the signature process.
        signature_starter = CadesSignatureStarter(get_restpki_client())

        # Set the signature policy.
        signature_starter.signature_policy_id = StandardSignaturePolicies.CADES_ICPBR_ADR_BASICA

        # Set a security context to be used to determine trust in the
        # certificate chain. We have encapsulated the security context choice on
        # util.py.
        signature_starter.security_context_id = get_security_context_id()

        # If the URL argument "userfile" is filled, it means the user was
        # redirected here by "upload" view (signature with file uploaded by
        # user). We'll set the path of the file to be signed, which was saved
        # in the app_data folder by "upload" view.
        if cmsfile is not None:
            signature_starter.set_cms_to_cosign_path('%s/%s' % (APPDATA_FOLDER,
                                                                cmsfile))
        elif userfile is not None:
            signature_starter.set_file_to_sign_path('%s/%s' % (APPDATA_FOLDER,
                                                               userfile))
        else:
            signature_starter.set_file_to_sign_path(
                '%s/%s' % (STATIC_FOLDER, 'SampleDocument.pdf'))

        # Optionally, set whether the content should be encapsulated in the
        # resulting CMS. If this parameter is ommitted, the following rules
        # apply:
        # - If no CmsToCoSign is given, the resulting CMS will include the
        # content;
        # - If a CmsToCoSign is given, the resulting CMS will include the
        # content if and only if the CmsToCoSign also includes the content.
        signature_starter.encapsulate_content = True

        # Call the start_with_webpki() method, which initiates the signature.
        # This yields the token, a 43-character case-sensitive URL-safe string,
        # which identifies this signature process. We'll use this value to call
        # the signWithRestPki() method on the Web PKI component (see
        # signature-form.js javascript) and also to complete the signature after
        # the form is submitted (see method action()). This should not be
        # mistaken with the API access token.
        token = signature_starter.start_with_webpki()

    except Exception as e:
        return render_template('error.html', msg=e)

    response = make_response(
        render_template('cades_signature/index.html', token=token,
                        userfile=userfile, cmsfile=cmsfile)
    )

    # The token acquired above can only be used for a single signature attempt.
    # In order to retry the signature it is necessary to get a new token. This
    # can be a problem if the user uses the back button of the browser, since
    # the browser might show a cached page that we rendered previously, with a
    # now stale token. To prevent this from happening, we call the method
    # set_no_cache_headers(). To prevent this from happen, we force page
    # expiration through HTTP headers to prevent caching of the page.
    response.headers = get_expired_page_headers()

    return response


@cades_signature.route('/action', methods=['POST'])
def action():
    """

    This method receives the form submission from the template. We'll call
    REST PKI to complete the signature.

    """

    # Get the token for this signature (rendered in a hidden input field, see
    # pades-signature.html template).
    token = request.form['token']

    # Get an instance of the CadesSignatureFinisher class, responsible for
    # completing the signature process.
    signature_finisher = CadesSignatureFinisher(get_restpki_client())

    # Set the token.
    signature_finisher.token = token

    # Call the finish() method, which finalizes the signature process and
    # returns the signed PDF.
    signature_finisher.finish()

    # Get information about the certificate used by the user to sign the file.
    # This method must only be called after calling the finish() method.
    signer_cert = signature_finisher.certificate

    # At this point, you'd typically store the signed PDF on your database. For
    # demonstration purposes, we'll store the PDF on a temporary folder publicly
    # accessible and render a link to it.

    filename = '%s.p7s' % (str(uuid.uuid1()))
    signature_finisher.write_cms(os.path.join(APPDATA_FOLDER, filename))

    return render_template('cades_signature/action.html', filename=filename,
                           signer_cert=signer_cert)
