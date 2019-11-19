from ..scripts.ldap_query import LDAPQuery
from .. import models
import transaction
from sqlalchemy import exc, func
from ..scripts.pt_mailer import PTMailer
from ..scripts.ldap_query import LDAPQuery
import json

class Utils():

    @classmethod
    def get_connected_user_id(cls, request):

        try:
            settings = request.registry.settings
            request.dbsession.execute('set search_path to ' + settings['schema_name'])
            connected_user = LDAPQuery.get_connected_user(request)
            login_attr = settings['ldap_user_attribute_login']

            if connected_user and login_attr in connected_user:
                login = connected_user[login_attr]

                query = request.dbsession.query(models.Contact.id).filter(func.lower(models.Contact.login) == func.lower(login)).first()

                if query and len(query) > 0:
                    return query[0]

        except Exception as error:
            raise error

        return None

    @classmethod
    def get_connected_user_from_db(cls, request):
        connected_user_id = None
        try:
            settings = request.registry.settings
            request.dbsession.execute('set search_path to ' + settings['schema_name'])
            connected_user = LDAPQuery.get_connected_user(request)
            login_attr = settings['ldap_user_attribute_login']

            if connected_user and login_attr in connected_user:
                login = connected_user[login_attr]

                return request.dbsession.query(models.Contact).filter(
                    func.lower(models.Contact.login) == func.lower(login)).first()

        except Exception as error:
            raise error

        return None


    @classmethod
    def mise_a_jour_groupes_ad(cls, request):
        try:
            settings = request.registry.settings
            request.dbsession.execute('set search_path to ' + settings['schema_name'])
            login_attr = settings['ldap_user_attribute_login']

            # Logins from AD
            contacts_ad_json = LDAPQuery.get_users_belonging_to_group_entites(request)

            # Logins from DB
            contacts_bd_logins = []
            contacts_bd_logins_id = {}
            contacts_bd_logins_query = request.dbsession.query(models.Contact).distinct(models.Contact.login).filter(
                models.Contact.login.isnot(None)).all()

            # Logins from BD
            for c in contacts_bd_logins_query:
                contacts_bd_logins.append(c.login)
                contacts_bd_logins_id[c.login] = c.id

            # Entites from DB
            entites = {}
            entites_query = request.dbsession.query(models.Entite).all()
            for e in entites_query:
                entites[e.nom_groupe_ad] = e.id

            with transaction.manager as tm:
                for one_contact_ad_json in contacts_ad_json:
                    if one_contact_ad_json and login_attr in one_contact_ad_json:
                        one_contact_ad_login = one_contact_ad_json[login_attr];

                        # Login exists in BD logins
                        if one_contact_ad_login in contacts_bd_logins:
                            #one_contact_ad_dn = one_contact_ad_json['dn']
                            one_contact_bd_id = contacts_bd_logins_id[one_contact_ad_login]
                            contact_ldap_groups = LDAPQuery.get_user_groups(request, one_contact_ad_login)

                            # Delete all AD groups relationships of the contact
                            request.dbsession.query(models.FonctionContact).filter(
                                models.FonctionContact.id_contact == one_contact_bd_id).delete(synchronize_session=False)
                            request.dbsession.query(models.LienContactEntite).filter(
                                models.LienContactEntite.id_contact == one_contact_bd_id).delete(synchronize_session=False)

                            for one_contact_ldap_group_item in contact_ldap_groups:

                                one_contact_ldap_group_id = one_contact_ldap_group_item[
                                    settings['ldap_group_attribute_id']]
                                one_contact_ldap_group_name = one_contact_ldap_group_item[
                                    settings['ldap_group_attribute_name']]

                                # Entite group
                                if one_contact_ldap_group_name.startswith(settings['ldap_entite_groups_prefix']):
                                    id_entite = entites[
                                        one_contact_ldap_group_name] if one_contact_ldap_group_name in entites else None

                                    # If entite AD group does not exist is in DB, add it
                                    if id_entite is None:
                                        entite_model = models.Entite(
                                            nom=one_contact_ldap_group_name,
                                            id_responsable=settings['id_responsable_entite'],
                                            nom_groupe_ad=one_contact_ldap_group_id
                                        )
                                        request.dbsession.add(entite_model)
                                        request.dbsession.flush()
                                        id_entite = entite_model.id

                                    lien_entite_contact_model = models.LienContactEntite(
                                        id_contact=one_contact_bd_id,
                                        id_entite=id_entite
                                    )
                                    request.dbsession.add(lien_entite_contact_model)


                                # Fonction group
                                elif one_contact_ldap_group_name.startswith(settings['ldap_fonction_groups_prefix']):
                                    fonction_contact_model = models.FonctionContact(
                                        id_contact=one_contact_bd_id,
                                        fonction=one_contact_ldap_group_name
                                    )
                                    request.dbsession.add(fonction_contact_model)

            transaction.commit()

        except Exception as e:
            transaction.abort()
            request.dbsession.rollback()
            raise Exception(e)

        return True

    @classmethod
    def get_contacts_mails_by_ids(cls, request, ids):
        contacts_mails = []

        try:
            settings = request.registry.settings
            request.dbsession.execute('set search_path to ' + settings['schema_name'])
            contacts_query = request.dbsession.query(models.Contact.courriel).filter(models.Contact.id.in_(ids)).all()

            for c in contacts_query:
                contacts_mails.append(c.courriel)

        except Exception as error:
            raise error

        return contacts_mails

    @classmethod
    def send_mail_to_contacts_belonging_to_a_group(cls, request, group_name, subject, body):
        try:

            users = LDAPQuery.get_users_belonging_to_a_group(request, group_name);
            mail_att_name = request.registry.settings['ldap_user_attribute_mail']
            recipients = [x[mail_att_name] for x in users if mail_att_name in x]

            if recipients and len(recipients) > 0 :
                return PTMailer.send_mail(request, recipients, subject, body)

        except Exception as error:
            raise error

        return  False

    @classmethod
    def get_mails_of_contacts_belonging_to_a_group(cls, request, group_name):
        recipients = []

        try:

            users = LDAPQuery.get_users_belonging_to_a_group(request, group_name);
            mail_att_name = request.registry.settings['ldap_user_attribute_mail']
            recipients = [x[mail_att_name] for x in users if mail_att_name in x]

        except Exception as error:
            raise error

        return recipients

    @classmethod
    def compare_perturbation_geometries(cls, request, id_perturbation, input_geometries):
        try:

           points_query = request.dbsession.query(func.public.st_asgeojson(models.PerturbationPoint.geometry)).filter(
                models.PerturbationPoint.id_perturbation == id_perturbation).all()

           lignes_query = request.dbsession.query(func.public.st_asgeojson(models.PerturbationLigne.geometry)).filter(
                models.PerturbationLigne.id_perturbation == id_perturbation).all()

           count_points_db = len(points_query)
           count_lignes_db = len(lignes_query)

           if (input_geometries is None or input_geometries == '') and (count_points_db > 0 or count_lignes_db > 0):
               return False

           elif input_geometries is None or  input_geometries == '':
               return True

           count_points_input_geom = 0
           count_lignes_input_geom = 0

           json_geometries = json.loads(input_geometries)

           # 1) Check geometries number
           for onegeojson in json_geometries:
               if 'geometry' in onegeojson:
                   geometry = onegeojson['geometry']

                   if 'type' in geometry:
                       type_geom = geometry['type']

                       if type_geom == 'Point':
                           count_points_input_geom += 1

                       # Line
                       elif type_geom == 'LineString' or type_geom == 'MultiLineString' or type_geom == 'GeometryCollection':
                           count_lignes_input_geom += 1

           if (count_points_input_geom + count_lignes_input_geom) != (count_points_db + count_lignes_db):
               return False

           # 2) Check geometries are the same
           else:

               for one_geom in points_query:
                   for onegeojson in json_geometries:
                       if 'geometry' in onegeojson:
                           geometry = onegeojson['geometry']

                           if 'type' in geometry:
                               type_geom = geometry['type']

                               if type_geom == 'Point':
                                   is_equal = cls.geometry_exists_in_array_of_geometries(request, geometry, points_query)

                                   if is_equal == False:
                                       return False

                               # Line
                               elif type_geom == 'LineString' or type_geom == 'MultiLineString' or type_geom == 'GeometryCollection':
                                   is_equal = cls.geometry_exists_in_array_of_geometries(request, geometry, lignes_query)

                                   if is_equal == False:
                                       return False

        except Exception as error:
            raise error

        return True

    @classmethod
    def geometry_exists_in_array_of_geometries(cls, request, geometry, input_geometries):
        settings = request.registry.settings
        request.dbsession.execute('set search_path to ' + settings['schema_name'])
        first_geom_str = "public.ST_GeomFromGeoJSON('" + str(geometry).replace("'", '"') + "')"

        for one_geom in input_geometries:
            if len(one_geom) > 0:
                one_geom = one_geom[0]

            second_geom_str = "public.ST_GeomFromGeoJSON('" + one_geom + "')"
            query_str = "SELECT public.ST_Equals(" + first_geom_str + ", " + second_geom_str + ")"

            is_equal = request.dbsession.execute(query_str).first()
            is_equal = is_equal[0] if is_equal and len(is_equal) > 0 else None
            is_equal = True if str(is_equal).lower() == "true" else False

            if is_equal == True:
                return True

        return False

    @classmethod
    def user_can_read_evenement(cls, request, current_user_id, id_evenement):
        try:
            if current_user_id is None:
                return False

            query_permission = request.dbsession.query(models.EvenementPourUtilisateurLecture).filter(models.EvenementPourUtilisateurLecture.id_utilisateur == current_user_id).filter(models.EvenementPourUtilisateurLecture.id_evenement == id_evenement).first()

            if not query_permission:
                return False

        except Exception as error:
            raise error

        return True

    @classmethod
    def user_can_add_evenement(cls, request, current_user_id):
        try:
            if current_user_id is None:
                return False

            query_permission = request.dbsession.query(models.AutorisationFonction).filter(
                models.AutorisationFonction.id_utilisateur == current_user_id).filter(models.AutorisationFonction.ajouter_evenement == True).first()

            if not query_permission:
                return False

        except Exception as error:
            raise error

        return True

    @classmethod
    def user_can_update_evenement(cls, request, current_user_id, id_evenement):
        try:
            if current_user_id is None:
                return False

            query_permission = request.dbsession.query(models.EvenementPourUtilisateurModification).filter(
                models.EvenementPourUtilisateurModification.id_utilisateur == current_user_id).filter(models.EvenementPourUtilisateurModification.id_evenement == id_evenement).first()

            if not query_permission:
                return False

        except Exception as error:
            raise error

        return True

    @classmethod
    def user_can_delete_evenement(cls, request, current_user_id, id_evenement):
        try:
            if current_user_id is None:
                return False

            query_permission = request.dbsession.query(models.EvenementPourUtilisateurSuppression).filter(
                models.EvenementPourUtilisateurSuppression.id_utilisateur == current_user_id).filter(models.EvenementPourUtilisateurSuppression.id_evenement == id_evenement).first()

            if not query_permission:
                return False

        except Exception as error:
            raise error

        return True

    @classmethod
    def user_can_read_perturbation(cls, request, current_user_id, id_perturbation):
        try:
            if current_user_id is None:
                return False

            query_permission = request.dbsession.query(models.PerturbationPourUtilisateurLecture).filter(
                models.PerturbationPourUtilisateurLecture.id_utilisateur == current_user_id).filter(models.PerturbationPourUtilisateurLecture.id_perturbation == id_perturbation).first()

            if not query_permission:
                return False

        except Exception as error:
            raise error

        return True

    @classmethod
    def user_can_add_perturbation(cls, request, current_user_id, id_evenement, id_entite):
        try:
            if current_user_id is None:
                return False

            query_permission = request.dbsession.query(models.PerturbationPourUtilisateurAjout).filter(
                models.PerturbationPourUtilisateurAjout.id_utilisateur == current_user_id).filter(models.PerturbationPourUtilisateurAjout.id_evenement == id_evenement).filter(models.PerturbationPourUtilisateurAjout.id_entite == id_entite).first()

            if not query_permission:
                return False

        except Exception as error:
            raise error

        return True

    @classmethod
    def user_can_update_perturbation(cls, request, current_user_id, id_perturbation):
        try:
            if current_user_id is None:
                return False

            query_permission = request.dbsession.query(models.PerturbationPourUtilisateurModification).filter(
                models.PerturbationPourUtilisateurModification.id_utilisateur == current_user_id).filter(models.PerturbationPourUtilisateurModification.id_perturbation == id_perturbation).first()

            if not query_permission:
                return False

        except Exception as error:
            raise error

        return True

    @classmethod
    def user_can_delete_perturbation(cls, request, current_user_id, id_perturbation):
        try:
            if current_user_id is None:
                return False

            query_permission = request.dbsession.query(models.PerturbationPourUtilisateurSuppression).filter(
                models.PerturbationPourUtilisateurSuppression.id_utilisateur == current_user_id).filter(models.PerturbationPourUtilisateurSuppression.id_perturbation == id_perturbation).first()

            if not query_permission:
                return False

        except Exception as error:
            raise error

        return True

    @classmethod
    def user_can_update_etat_perturbation(cls, request, current_user_id, id_perturbation):
        try:
            if current_user_id is None:
                return False

            query_permission = request.dbsession.query(models.PerturbationPourUtilisateurModificationEtat).filter(
                    models.PerturbationPourUtilisateurModificationEtat.id_utilisateur == current_user_id).filter(models.PerturbationPourUtilisateurModificationEtat.id_perturbation == id_perturbation).first()

            if not query_permission:
                return False

        except Exception as error:
            raise error

        return True

    @classmethod
    def user_can_update_etat_perturbation_creation(cls, request, current_user_id):
        try:
            if current_user_id is None:
                return False

            query_permission = request.dbsession.query(models.AutorisationFonction).filter(
                models.AutorisationFonction.id_utilisateur == current_user_id).filter(
                models.AutorisationFonction.modifier_etat_perturbation_creation == True).first()

            if not query_permission:
                return False

        except Exception as error:
            raise error

        return True

    @classmethod
    def add_historique_etat_perturbation(cls, request, current_user_id, id_perturbation, etat):
        try:
            with transaction.manager:
                model = models.HistoriqueEtatPerturbation(
                    id_perturbation=id_perturbation,
                    id_utilisateur=current_user_id,
                    etat=etat)

                request.dbsession.add(model)
                transaction.commit()

        except Exception as error:
            raise error

    @classmethod
    def get_mails_contacts_mails_fermeture_urgence(cls, request):
        mails = []
        try:
            query = request.dbsession.query(models.Contact, models.ContactAvisFermetureUrgence).filter(
                models.Contact.id == models.ContactAvisFermetureUrgence.id_contact).all()

            for c, caf in query:
                if c.courriel and not c.courriel in mails:
                    mails.append(c.courriel)


        except Exception as error:
            raise error

        return mails

    @classmethod
    def get_mails_contacts_pr_touche(cls, request):
        mails = []
        try:
            query = request.dbsession.query(models.Contact, models.ContactAvisPrTouche).filter(
                models.Contact.id == models.ContactAvisPrTouche.id_contact).all()

            for c, capt in query:
                if c.courriel and not c.courriel in mails:
                    mails.append(c.courriel)


        except Exception as error:
            raise error

        return mails

    @classmethod
    def check_evenement_pr_touche(cls, request, evenement_id):

        try:
            query = request.dbsession.query(models.SearchEvenementView.pr_touches).filter(
                models.SearchEvenementView.id == evenement_id).filter(models.SearchEvenementView.pr_touches == True).all()

            if query:
                return True


        except Exception as error:
            raise error

        return False

    @classmethod
    def create_perturbation_mail_dict(cls, request, perturbation_model, evenement_record, deviation):
        settings = request.registry.settings
        concerne = 'Autre évènement : ' if int(evenement_record.type) == int(
            settings['autre_evenement_id']) else 'Chantier : ' if int(
            evenement_record.type) == int(
            settings['chantier_evenement_id']) else 'Manifestation : ' if int(
            evenement_record.type) == int(
            settings['manifestation_evenement_id']) else 'Fouille : ' if int(
            evenement_record.type) == int(settings['fouille_evenement_id']) else ''
        concerne += evenement_record.libelle

        if evenement_record.numero_dossier is not None:
            concerne += ' (' + evenement_record.numero_dossier + ')'

        mail_dict = {
            'type': 'la fermeture' if int(perturbation_model.type) == int(settings['fermeture_perturbation_id']) else "L'occupation" if int(perturbation_model.type) == int(settings['occupation_perturbation_id']) else '',
            'etat': 'Acceptée' if int(perturbation_model.etat) == int(
                settings['perturbation_etat_acceptee_code']) else 'Réfusée' if int(perturbation_model.etat) == int(
                settings['perturbation_etat_refusee_code']) else 'En attente',
            'urgence': 'Oui' if perturbation_model.urgence else 'Non',
            'concerne': concerne,
            'description': perturbation_model.description,
            'localite': perturbation_model.localisation,
            'date_debut': perturbation_model.date_debut,
            'heure_debut': perturbation_model.heure_debut,
            'date_fin': perturbation_model.date_fin,
            'heure_fin': perturbation_model.heure_fin,
            'tranche_horaire': 'Oui' if perturbation_model.tranche_horaire else 'Non',
            'nom_responsable_trafic': perturbation_model.nom_responsable_trafic,
            'prenom_responsable_trafic': perturbation_model.prenom_responsable_trafic,
            'telephone_responsable_trafic': perturbation_model.telephone_responsable_trafic,
            'mobile_responsable_trafic': perturbation_model.mobile_responsable_trafic,
            'courriel_responsable_trafic': perturbation_model.courriel_responsable_trafic,
            'deviation': deviation if deviation else ''
        }


        return mail_dict

    @classmethod
    def try_parse_float(cls, string, fail=None):
        try:
            return float(string)
        except Exception:
            return string;

