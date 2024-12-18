# This file is based on templates provided and copyrighted by Autodesk, Inc.
# This file has been modified by Epic Games, Inc. and is subject to the license
# file included in this repository.

import sgtk
import unreal
from tank_vendor import six

import copy
import datetime
import os
import pprint
import subprocess
import sys
import tempfile

# Local storage path field for known Oses.
_OS_LOCAL_STORAGE_PATH_FIELD = {
    "darwin": "mac_path",
    "win32": "windows_path",
    "linux": "linux_path",
    "linux2": "linux_path",
}[sys.platform]

HookBaseClass = sgtk.get_hook_baseclass()

print("PUBLISH_MOVIE LOADING")
if 'WONJIN_PUBLISH_MOVIE' in os.environ:
    os.environ['WONJIN_PUBLISH_MOVIE'] += os.pathsep + 'PUBLISH_MOVIE_LOADING'
else:
    os.environ['WONJIN_PUBLISH_MOVIE'] = 'PUBLISH_MOVIE_LOADING'
class UnrealMoviePublishPlugin(HookBaseClass):
    """
    Plugin for publishing an Unreal sequence as a rendered movie file.

    This hook relies on functionality found in the base file publisher hook in
    the publish2 app and should inherit from it in the configuration. The hook
    setting for this plugin should look something like this::

        hook: "{self}/publish_file.py:{engine}/tk-multi-publish2/basic/publish_session.py"

    To learn more about writing a publisher plugin, visit
    http://developer.shotgunsoftware.com/tk-multi-publish2/plugin.html
    """
    def __init__(self, *args, **kwargs):
        super(UnrealMoviePublishPlugin, self).__init__(*args, **kwargs)
        print("PUBLISH_MOVIE INIT")
        if 'WONJIN_PUBLISH_MOVIE' in os.environ:
            os.environ['WONJIN_PUBLISH_MOVIE'] += os.pathsep + 'PUBLISH_MOVIE_INIT'
        else:
            os.environ['WONJIN_PUBLISH_MOVIE'] = 'PUBLISH_MOVIE_INIT'
    # NOTE: The plugin icon and name are defined by the base file plugin.

    @property
    def description(self):
        """
        Verbose, multi-line description of what the plugin does. This can
        contain simple html for formatting.
        """

        return """Publishes the sequence as a rendered movie to Shotgun. A
        <b>Publish</b> entry will be created in Shotgun which will include a
        reference to the movie's current path on disk. A <b>Version</b> entry
        will also be created in Shotgun with the movie file being uploaded
        there. Other users will be able to review the movie in the browser or
        in RV.
        <br>
        If available, the Movie Render Queue will be used for rendering,
        the Level Sequencer will be used otherwise.
        """

    @property
    def settings(self):
        """
        Dictionary defining the settings that this plugin expects to receive
        through the settings parameter in the accept, validate, publish and
        finalize methods.

        A dictionary on the following form::

            {
                "Settings Name": {
                    "type": "settings_type",
                    "default": "default_value",
                    "description": "One line description of the setting"
            }

        The type string should be one of the data types that toolkit accepts as
        part of its environment configuration.
        """

        # inherit the settings from the base publish plugin
        base_settings = super(UnrealMoviePublishPlugin, self).settings or {}

        # Here you can add any additional settings specific to this plugin
        publish_template_setting = {
            "Publish Template": {
                "type": "template",
                "default": None,
                "description": "Template path for published work files. Should"
                               "correspond to a template defined in "
                               "templates.yml.",
            },
            "Movie Render Queue Presets Path": {
                "type": "string",
                "default": None,
                "description": "Optional Unreal Path to saved presets "
                               "for rendering with the Movie Render Queue"
            },
            "Publish Folder": {
                "type": "string",
                "default": None,
                "description": "Optional folder to use as a root for publishes"
            }
        }

        # update the base settings
        base_settings.update(publish_template_setting)

        return base_settings

    @property
    def item_filters(self):
        """
        List of item types that this plugin is interested in.

        Only items matching entries in this list will be presented to the
        accept() method. Strings can contain glob patters such as *, for example
        ["maya.*", "file.maya"]
        """
        return ["unreal.asset.LevelSequence"]

    def create_settings_widget(self, parent):
        """
        Creates a Qt widget, for the supplied parent widget (a container widget
        on the right side of the publish UI).

        :param parent: The parent to use for the widget being created
        :return: A :class:`QtGui.QFrame` that displays editable widgets for
                 modifying the plugin's settings.
        """
        # defer Qt-related imports
        from sgtk.platform.qt import QtGui, QtCore

        # Create a QFrame with all our widgets
        settings_frame = QtGui.QFrame(parent)
        # Create our widgets, we add them as properties on the QFrame so we can
        # retrieve them easily. Qt uses camelCase so our xxxx_xxxx names can't
        # clash with existing Qt properties.

        # Show this plugin description
        settings_frame.description_label = QtGui.QLabel(self.description)
        settings_frame.description_label.setWordWrap(True)
        settings_frame.description_label.setOpenExternalLinks(True)
        settings_frame.description_label.setTextFormat(QtCore.Qt.RichText)

        # Unreal setttings
        settings_frame.unreal_render_presets_label = QtGui.QLabel("Render with Movie Pipeline Presets:")
        settings_frame.unreal_render_presets_widget = QtGui.QComboBox()
        settings_frame.unreal_render_presets_widget.addItem("No presets")
        presets_folder = unreal.MovieRenderPipelineProjectSettings().preset_save_dir
        for preset in unreal.EditorAssetLibrary.list_assets(presets_folder.path):
            settings_frame.unreal_render_presets_widget.addItem(preset.split(".")[0])

        settings_frame.unreal_publish_folder_label = QtGui.QLabel("Publish folder:")
        storage_roots = self.parent.shotgun.find(
            "LocalStorage",
            [],
            ["code", _OS_LOCAL_STORAGE_PATH_FIELD]
        )
        settings_frame.storage_roots_widget = QtGui.QComboBox()
        settings_frame.storage_roots_widget.addItem("Current Unreal Project")
        for storage_root in storage_roots:
            if storage_root[_OS_LOCAL_STORAGE_PATH_FIELD]:
                settings_frame.storage_roots_widget.addItem(
                    "%s (%s)" % (
                        storage_root["code"],
                        storage_root[_OS_LOCAL_STORAGE_PATH_FIELD]
                    ),
                    userData=storage_root,
                )
        # Create the layout to use within the QFrame
        settings_layout = QtGui.QVBoxLayout()
        settings_layout.addWidget(settings_frame.description_label)
        settings_layout.addWidget(settings_frame.unreal_render_presets_label)
        settings_layout.addWidget(settings_frame.unreal_render_presets_widget)
        settings_layout.addWidget(settings_frame.unreal_publish_folder_label)
        settings_layout.addWidget(settings_frame.storage_roots_widget)

        settings_layout.addStretch()
        settings_frame.setLayout(settings_layout)
        return settings_frame

    def get_ui_settings(self, widget):
        """
        Method called by the publisher to retrieve setting values from the UI.

        :returns: A dictionary with setting values.
        """
        # defer Qt-related imports
        from sgtk.platform.qt import QtCore

        self.logger.info("Getting settings from UI")

        # Please note that we don't have to return all settings here, just the
        # settings which are editable in the UI.
        render_presets_path = None
        if widget.unreal_render_presets_widget.currentIndex() > 0:  # First entry is "No Presets"
            render_presets_path = six.ensure_str(widget.unreal_render_presets_widget.currentText())
        storage_index = widget.storage_roots_widget.currentIndex()
        publish_folder = None
        if storage_index > 0:  # Something selected and not the first entry
            storage = widget.storage_roots_widget.itemData(storage_index, role=QtCore.Qt.UserRole)
            publish_folder = storage[_OS_LOCAL_STORAGE_PATH_FIELD]

        settings = {
            "Movie Render Queue Presets Path": render_presets_path,
            "Publish Folder": publish_folder,
        }
        return settings

    def set_ui_settings(self, widget, settings):
        """
        Method called by the publisher to populate the UI with the setting values.

        :param widget: A QFrame we created in `create_settings_widget`.
        :param settings: A list of dictionaries.
        :raises NotImplementedError: if editing multiple items.
        """
        # defer Qt-related imports
        from sgtk.platform.qt import QtCore

        self.logger.info("Setting UI settings")
        if len(settings) > 1:
            # We do not allow editing multiple items
            raise NotImplementedError
        cur_settings = settings[0]
        render_presets_path = cur_settings["Movie Render Queue Presets Path"]
        preset_index = 0
        if render_presets_path:
            preset_index = widget.unreal_render_presets_widget.findText(render_presets_path)
            self.logger.info("Index for %s is %s" % (render_presets_path, preset_index))
        widget.unreal_render_presets_widget.setCurrentIndex(preset_index)
        # Note: the template is validated in the accept method, no need to check it here.
        publish_template_setting = cur_settings.get("Publish Template")
        publisher = self.parent
        publish_template = publisher.get_template_by_name(publish_template_setting)
        if isinstance(publish_template, sgtk.TemplatePath):
            widget.unreal_publish_folder_label.setEnabled(False)
            widget.storage_roots_widget.setEnabled(False)
        folder_index = 0
        publish_folder = cur_settings["Publish Folder"]
        if publish_folder:
            for i in range(widget.storage_roots_widget.count()):
                data = widget.storage_roots_widget.itemData(i, role=QtCore.Qt.UserRole)
                if data and data[_OS_LOCAL_STORAGE_PATH_FIELD] == publish_folder:
                    folder_index = i
                    break
            self.logger.debug("Index for %s is %s" % (publish_folder, folder_index))
        widget.storage_roots_widget.setCurrentIndex(folder_index)

    def load_saved_ui_settings(self, settings):
        """
        Load saved settings and update the given settings dictionary with them.

        :param settings: A dictionary where keys are settings names and
                         values Settings instances.
        """
        # Retrieve SG utils framework settings module and instantiate a manager
        fw = self.load_framework("tk-framework-shotgunutils_v5.x.x")
        module = fw.import_module("settings")
        settings_manager = module.UserSettings(self.parent)

        # Retrieve saved settings
        settings["Movie Render Queue Presets Path"].value = settings_manager.retrieve(
            "publish2.movie_render_queue_presets_path",
            settings["Movie Render Queue Presets Path"].value,
            settings_manager.SCOPE_PROJECT,
        )
        settings["Publish Folder"].value = settings_manager.retrieve(
            "publish2.publish_folder",
            settings["Publish Folder"].value,
            settings_manager.SCOPE_PROJECT
        )
        self.logger.debug("Loaded settings %s" % settings["Publish Folder"])
        self.logger.debug("Loaded settings %s" % settings["Movie Render Queue Presets Path"])

    def save_ui_settings(self, settings):
        """
        Save UI settings.

        :param settings: A dictionary of Settings instances.
        """
        # Retrieve SG utils framework settings module and instantiate a manager
        fw = self.load_framework("tk-framework-shotgunutils_v5.x.x")
        module = fw.import_module("settings")
        settings_manager = module.UserSettings(self.parent)

        # Save settings
        render_presets_path = settings["Movie Render Queue Presets Path"].value
        settings_manager.store("publish2.movie_render_queue_presets_path", render_presets_path, settings_manager.SCOPE_PROJECT)
        publish_folder = settings["Publish Folder"].value
        settings_manager.store("publish2.publish_folder", publish_folder, settings_manager.SCOPE_PROJECT)

    def accept(self, settings, item):
        """
        Method called by the publisher to determine if an item is of any
        interest to this plugin. Only items matching the filters defined via the
        item_filters property will be presented to this method.

        A publish task will be generated for each item accepted here. Returns a
        dictionary with the following booleans:

            - accepted: Indicates if the plugin is interested in this value at
                all. Required.
            - enabled: If True, the plugin will be enabled in the UI, otherwise
                it will be disabled. Optional, True by default.
            - visible: If True, the plugin will be visible in the UI, otherwise
                it will be hidden. Optional, True by default.
            - checked: If True, the plugin will be checked in the UI, otherwise
                it will be unchecked. Optional, True by default.

        :param settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process

        :returns: dictionary with boolean keys accepted, required and enabled
        """

        accepted = True
        checked = True

        if sys.platform != "win32":
            self.logger.warning(
                "Movie publishing is not supported on other platforms than Windows..."
            )
            return {
                "accepted": False,
            }

        publisher = self.parent
        # ensure the publish template is defined
        publish_template_setting = settings.get("Publish Template")
        publish_template = publisher.get_template_by_name(publish_template_setting.value)
        if not publish_template:
            self.logger.debug(
                "A publish template could not be determined for the "
                "item. Not accepting the item."
            )
            accepted = False

        # we've validated the work and publish templates. add them to the item properties
        # for use in subsequent methods
        item.properties["publish_template"] = publish_template
        self.load_saved_ui_settings(settings)
        return {
            "accepted": accepted,
            "checked": checked
        }

    def validate(self, settings, item):
        """
        Validates the given item to check that it is ok to publish. Returns a
        boolean to indicate validity.

        :param settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process
        :returns: True if item is valid, False otherwise.
        """
        # raise an exception here if something is not valid.
        # If you use the logger, warnings will appear in the validation tree.
        # You can attach callbacks that allow users to fix these warnings
        # at the press of a button.
        #
        # For example:
        #
        # self.logger.info(
        #         "Your session is not part of a maya project.",
        #         extra={
        #             "action_button": {
        #                 "label": "Set Project",
        #                 "tooltip": "Set the maya project",
        #                 "callback": lambda: mel.eval('setProject ""')
        #             }
        #         }
        #     )

        asset_path = item.properties.get("asset_path")
        asset_name = item.properties.get("asset_name")
        if not asset_path or not asset_name:
            self.logger.debug("Sequence path or name not configured.")
            return False
        # Retrieve the Level Sequences sections tree for this Level Sequence.
        # This is needed to get frame ranges in the "edit" context.
        edits_path = item.properties.get("edits_path")
        if not edits_path:
            self.logger.debug("Edits path not configured.")
            return False

        self.logger.info("Edits path %s" % edits_path)
        item.properties["unreal_master_sequence"] = edits_path[0]
        item.properties["unreal_shot"] = ".".join([lseq.get_name() for lseq in edits_path[1:]])
        self.logger.info("Master sequence %s, shot %s" % (
            item.properties["unreal_master_sequence"].get_name(),
            item.properties["unreal_shot"] or "all shots",
        ))
        # Get the configured publish template
        publish_template = item.properties["publish_template"]

        # Get the context from the Publisher UI
        context = item.context
        unreal.log("context: {}".format(context))

        # Query the fields needed for the publish template from the context
        try:
            fields = context.as_template_fields(publish_template)
        except Exception:
            # We likely failed because of folder creation, trigger that
            self.parent.sgtk.create_filesystem_structure(
                context.entity["type"],
                context.entity["id"],
                self.parent.engine.instance_name
            )
            # In theory, this should now work because we've created folders and
            # updated the path cache
            fields = item.context.as_template_fields(publish_template)
        unreal.log("context fields: {}".format(fields))

        # Ensure that the current map is saved on disk
        unreal_map = unreal.EditorLevelLibrary.get_editor_world()
        unreal_map_path = unreal_map.get_path_name()

        # Transient maps are not supported, must be saved on disk
        if unreal_map_path.startswith("/Temp/"):
            self.logger.debug("Current map must be saved first.")
            return False

        # Add the map name to fields
        world_name = unreal_map.get_name()
        # Add the Level Sequence to fields, with the shot if any
        fields["ue_world"] = world_name
        if len(edits_path) > 1:
            fields["ue_level_sequence"] = "%s_%s" % (edits_path[0].get_name(), edits_path[-1].get_name())
        else:
            fields["ue_level_sequence"] = edits_path[0].get_name()

        # Stash the level sequence and map paths in properties for the render
        item.properties["unreal_asset_path"] = asset_path
        item.properties["unreal_map_path"] = unreal_map_path

        # Add a version number to the fields, incremented from the current asset version
        version_number = self._unreal_asset_get_version(asset_path)
        version_number = version_number + 1
        fields["version"] = version_number

        # Add today's date to the fields
        date = datetime.date.today()
        fields["YYYY"] = date.year
        fields["MM"] = date.month
        fields["DD"] = date.day

        # Check if we can use the Movie Render queue available from 4.26
        use_movie_render_queue = False
        render_presets = None
        if hasattr(unreal, "MoviePipelineQueueEngineSubsystem"):
            if hasattr(unreal, "MoviePipelineAppleProResOutput"):
                use_movie_render_queue = True
                self.logger.info("Movie Render Queue will be used for rendering.")
                render_presets_path = settings["Movie Render Queue Presets Path"].value
                if render_presets_path:
                    self.logger.info("Validating render presets path %s" % render_presets_path)
                    render_presets = unreal.EditorAssetLibrary.load_asset(render_presets_path)
                    for _, reason in self._check_render_settings(render_presets):
                        self.logger.warning(reason)
            else:
                self.logger.info(
                    "Apple ProRes Media plugin must be loaded to be able to render with the Movie Render Queue, "
                    "Level Sequencer will be used for rendering."
                )

        if not use_movie_render_queue:
            if item.properties["unreal_shot"]:
                raise ValueError("Rendering invidual shots for a sequence is only supported with the Movie Render Queue.")
            self.logger.info("Movie Render Queue not available, Level Sequencer will be used for rendering.")

        item.properties["use_movie_render_queue"] = use_movie_render_queue
        item.properties["movie_render_queue_presets"] = render_presets
        # Set the UE movie extension based on the current platform and rendering engine
        if use_movie_render_queue:
            fields["ue_mov_ext"] = "mov"  # mov on all platforms
        else:
            if sys.platform == "win32":
                fields["ue_mov_ext"] = "avi"
            else:
                fields["ue_mov_ext"] = "mov"
        # Ensure the fields work for the publish template
        missing_keys = publish_template.missing_keys(fields)
        if missing_keys:
            error_msg = "Missing keys required for the publish template " \
                        "%s" % (missing_keys)
            self.logger.error(error_msg)
            raise ValueError(error_msg)

        publish_path = publish_template.apply_fields(fields)
        if not os.path.isabs(publish_path):
            # If the path is not absolute, prepend the publish folder setting.
            publish_folder = settings["Publish Folder"].value
            if not publish_folder:
                publish_folder = unreal.Paths.project_saved_dir()
            publish_path = os.path.abspath(
                os.path.join(
                    publish_folder,
                    publish_path
                )
            )
        item.properties["path"] = publish_path
        item.properties["publish_path"] = publish_path
        item.properties["publish_type"] = "Unreal Render"
        item.properties["version_number"] = version_number
        self.save_ui_settings(settings)
        return True

    def _check_render_settings(self, render_config):
        """
        Check settings from the given render preset and report which ones are problematic and why.

        :param render_config: An Unreal Movie Pipeline render config.
        :returns: A potentially empty list of tuples, where each tuple is a setting and a string explaining the problem.
        """
        invalid_settings = []
        # To avoid having multiple outputs, only keep the main render pass and the expected output format.
        for setting in render_config.get_all_settings():
            # Check for render passes. Since some classes derive from MoviePipelineDeferredPassBase, which is what we want to only keep
            # we can't use isinstance and use type instead.
            if isinstance(setting, unreal.MoviePipelineImagePassBase) and type(setting) != unreal.MoviePipelineDeferredPassBase:
                invalid_settings.append((setting, "Render pass %s would cause multiple outputs" % setting.get_name()))
            # Check rendering outputs
            elif isinstance(setting, unreal.MoviePipelineOutputBase) and not isinstance(setting, unreal.MoviePipelineAppleProResOutput):
                invalid_settings.append((setting, "Render output %s would cause multiple outputs" % setting.get_name()))
        return invalid_settings

    def publish(self, settings, item):
        """
        Executes the publish logic for the given item and settings.

        :param settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process
        """

        # This is where you insert custom information into `item`, like the
        # path of the file being published or any dependency this publish
        # has on other publishes.

        # get the path in a normalized state. no trailing separator, separators
        # are appropriate for current os, no double separators, etc.

        # let the base class register the publish

        publish_path = os.path.normpath(item.properties["publish_path"])

        # Split the destination path into folder and filename
        destination_folder, movie_name = os.path.split(publish_path)
        movie_name = os.path.splitext(movie_name)[0]

        # Ensure that the destination path exists before rendering the sequence
        self.parent.ensure_folder_exists(destination_folder)

        # Get the level sequence and map paths again
        unreal_asset_path = item.properties["unreal_asset_path"]
        unreal_map_path = item.properties["unreal_map_path"]
        unreal.log("movie name: {}".format(movie_name))
        # Render the movie
        if item.properties.get("use_movie_render_queue"):
            presets = item.properties["movie_render_queue_presets"]
            if presets:
                self.logger.info("Rendering %s with the Movie Render Queue with %s presets." % (publish_path, presets.get_name()))
            else:
                self.logger.info("Rendering %s with the Movie Render Queue." % publish_path)
            res, _ = self._unreal_render_sequence_with_movie_queue(
                publish_path,
                unreal_map_path,
                unreal_asset_path,
                presets,
                item.properties.get("unreal_shot") or None,
            )
        else:
            self.logger.info("Rendering %s with the Level Sequencer." % publish_path)
            res, _ = self._unreal_render_sequence_with_sequencer(
                publish_path,
                unreal_map_path,
                unreal_asset_path
            )
        if not res:
            raise RuntimeError(
                "Unable to render %s" % publish_path
            )
        # Increment the version number
        self._unreal_asset_set_version(unreal_asset_path, item.properties["version_number"])

        # Publish the movie file to Shotgun
        super(UnrealMoviePublishPlugin, self).publish(settings, item)

        # Create a Version entry linked with the new publish
        # Populate the version data to send to SG
        self.logger.info("Creating Version...")
        version_data = {
            "project": item.context.project,
            "code": movie_name,
            "description": item.description,
            "entity": self._get_version_entity(item),
            "sg_path_to_movie": publish_path,
            "sg_task": item.context.task
        }

        publish_data = item.properties.get("sg_publish_data")

        # If the file was published, add the publish data to the version
        if publish_data:
            version_data["published_files"] = [publish_data]

        # Log the version data for debugging
        self.logger.debug(
            "Populated Version data...",
            extra={
                "action_show_more_info": {
                    "label": "Version Data",
                    "tooltip": "Show the complete Version data dictionary",
                    "text": "<pre>%s</pre>" % (
                        pprint.pformat(version_data),
                    )
                }
            }
        )

        # Create the version
        self.logger.info("Creating version for review...")
        version = self.parent.shotgun.create("Version", version_data)

        # Stash the version info in the item just in case
        item.properties["sg_version_data"] = version

        # On windows, ensure the path is utf-8 encoded to avoid issues with
        # the shotgun api
        upload_path = str(item.properties.get("publish_path"))
        unreal.log("upload_path: {}".format(upload_path))

        # Upload the file to SG
        self.logger.info("Uploading content...")
        self.parent.shotgun.upload(
            "Version",
            version["id"],
            upload_path,
            "sg_uploaded_movie"
        )
        self.logger.info("Upload complete!")

    def finalize(self, settings, item):
        """
        Execute the finalization pass. This pass executes once all the publish
        tasks have completed, and can for example be used to version up files.

        :param settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process
        """
        # do the base class finalization
        super(UnrealMoviePublishPlugin, self).finalize(settings, item)

    def _get_version_entity(self, item):
        """
        Returns the best entity to link the version to.
        """
        if item.context.entity:
            return item.context.entity
        elif item.context.project:
            return item.context.project
        else:
            return None

    def _unreal_asset_get_version(self, asset_path):
        asset = unreal.EditorAssetLibrary.load_asset(asset_path)
        version_number = 0

        if not asset:
            return version_number

        engine = sgtk.platform.current_engine()
        tag = engine.get_metadata_tag("version_number")

        metadata = unreal.EditorAssetLibrary.get_metadata_tag(asset, tag)

        if not metadata:
            return version_number

        try:
            version_number = int(metadata)
        except ValueError:
            pass

        return version_number

    def _unreal_asset_set_version(self, asset_path, version_number):
        asset = unreal.EditorAssetLibrary.load_asset(asset_path)

        if not asset:
            return

        engine = sgtk.platform.current_engine()
        tag = engine.get_metadata_tag("version_number")

        unreal.EditorAssetLibrary.set_metadata_tag(asset, tag, str(version_number))
        unreal.EditorAssetLibrary.save_loaded_asset(asset)

        # The save will pop up a progress bar that will bring the editor to the front thus hiding the publish app dialog
        # Workaround: Force all Shotgun dialogs to be brought to front
        engine = sgtk.platform.current_engine()
        for dialog in engine.created_qt_dialogs:
            dialog.raise_()

    def _unreal_render_sequence_with_sequencer(self, output_path, unreal_map_path, sequence_path):
        """
        Renders a given sequence in a given level to a movie file with the Level Sequencer.

        :param str output_path: Full path to the movie to render.
        :param str unreal_map_path: Path of the Unreal map in which to run the sequence.
        :param str sequence_path: Content Browser path of sequence to render.
        :returns: True if a movie file was generated, False otherwise
                  string representing the path of the generated movie file
        """
        output_folder, output_file = os.path.split(output_path)
        movie_name = os.path.splitext(output_file)[0]

        # First, check if there's a file that will interfere with the output of the Sequencer
        # Sequencer can only render to avi or mov file format
        if os.path.isfile(output_path):
            # Must delete it first, otherwise the Sequencer will add a number in the filename
            try:
                os.remove(output_path)
            except OSError:
                self.logger.error(
                    "Couldn't delete {}. The Sequencer won't be able to output the movie to that file.".format(output_path)
                )
                return False, None

        # Render the sequence to a movie file using the following command-line arguments
        cmdline_args = [
            sys.executable,  # Unreal executable path
            "%s" % os.path.join(
                unreal.SystemLibrary.get_project_directory(),
                "%s.uproject" % unreal.SystemLibrary.get_game_name(),
            ),  # Unreal project
            unreal_map_path,  # Level to load for rendering the sequence
            # Command-line arguments for Sequencer Render to Movie
            # See: https://docs.unrealengine.com/en-us/Engine/Sequencer/Workflow/RenderingCmdLine
            #
            "-LevelSequence=%s" % sequence_path,  # The sequence to render
            "-MovieFolder=%s" % output_folder,  # Output folder, must match the work template
            "-MovieName=%s" % movie_name,  # Output filename
            "-game",
            "-MovieSceneCaptureType=/Script/MovieSceneCapture.AutomatedLevelSequenceCapture",
            "-ResX=1280",
            "-ResY=720",
            "-ForceRes",
            "-Windowed",
            "-MovieCinematicMode=yes",
            "-MovieFormat=Video",
            "-MovieFrameRate=24",
            "-MovieQuality=75",
            "-NoTextureStreaming",
            "-NoLoadingScreen",
            "-NoScreenMessages",
        ]

        unreal.log(
            "Sequencer command-line arguments: {}".format(
                " ".join(cmdline_args)
            )
        )

        # Make a shallow copy of the current environment and clear some variables
        run_env = copy.copy(os.environ)
        # Prevent SG TK to try to bootstrap in the new process
        if "UE_SHOTGUN_BOOTSTRAP" in run_env:
            del run_env["UE_SHOTGUN_BOOTSTRAP"]
        if "UE_SHOTGRID_BOOTSTRAP" in run_env:
            del run_env["UE_SHOTGRID_BOOTSTRAP"]

        subprocess.call(cmdline_args, env=run_env)

        return os.path.isfile(output_path), output_path

    def _unreal_render_sequence_with_movie_queue(self, output_path, unreal_map_path, sequence_path, presets=None, shot_name=None):
        """
        Renders a given sequence in a given level with the Movie Render queue using EXR output.
        """
        output_folder, output_file = os.path.split(output_path)
        sequence_name = os.path.splitext(output_file)[0]

        qsub = unreal.MoviePipelineQueueEngineSubsystem()
        queue = qsub.get_queue()
        job = queue.allocate_new_job(unreal.MoviePipelineExecutorJob)
        
        # Load sequence asset to get frame range
        sequence = unreal.EditorAssetLibrary.load_asset(sequence_path)
        if not sequence:
            raise RuntimeError(f"Failed to load sequence: {sequence_path}")

        # Get sequence frame range
        fps = sequence.get_display_rate()
        start_frame = sequence.get_playback_start()
        end_frame = sequence.get_playback_end()
        
        # Convert frame times to frame numbers
        start_frame_number = int(start_frame.frame_number)
        end_frame_number = int(end_frame.frame_number)

        # Configure job
        job.sequence = unreal.SoftObjectPath(sequence_path)
        job.map = unreal.SoftObjectPath(unreal_map_path)

        # Configure the output settings
        config = job.get_configuration()
        output_setting = config.find_or_add_setting_by_class(unreal.MoviePipelineOutputSetting)
        output_setting.output_directory = unreal.DirectoryPath(output_folder)
        output_setting.output_resolution = unreal.IntPoint(1920, 1080)
        output_setting.file_name_format = sequence_name
        output_setting.override_existing_output = True
        
        # Set frame range
        frame_setting = config.find_or_add_setting_by_class(unreal.MoviePipelineFrameSetting)
        if frame_setting:
            self.logger.info(f"Setting frame range: {start_frame_number} to {end_frame_number}")
            frame_setting.start_frame = start_frame_number
            frame_setting.end_frame = end_frame_number
            frame_setting.custom_start_frame = start_frame  # Original frame time
            frame_setting.custom_end_frame = end_frame      # Original frame time
            frame_setting.use_custom_start_frame = True
            frame_setting.use_custom_end_frame = True
            
        # Configure EXR output
        exr_output = config.find_or_add_setting_by_class(unreal.MoviePipelineImageSequenceOutput_EXR)
        exr_output.output_file_name_format = "{sequence_name}.{frame_number:04d}"
        exr_output.compression = unreal.EXRCompressionFormat.ZIP
        
        # Add render pass
        config.find_or_add_setting_by_class(unreal.MoviePipelineDeferredPassBase)
        
        # Execute render using PIE
        executor = unreal.MoviePipelinePIEExecutor()
        qsub.render_queue_with_executor_instance(executor)

        # Check if files were generated
        expected_frames = end_frame_number - start_frame_number + 1
        output_files = [f for f in os.listdir(output_folder) if f.endswith('.exr')]
        
        # Verify frame range
        rendered_frames = len(output_files)
        if rendered_frames != expected_frames:
            self.logger.warning(
                f"Expected {expected_frames} frames but got {rendered_frames} frames"
            )
            return False, None
            
        return True, output_folder
class UnrealEXRPublishPlugin(HookBaseClass):
    """
    Plugin for publishing an Unreal sequence as EXR image sequences.

    This hook relies on functionality found in the base file publisher hook in
    the publish2 app and should inherit from it in the configuration. The hook
    setting for this plugin should look something like this::

        hook: "{self}/publish_file.py:{engine}/tk-multi-publish2/basic/publish_session.py"
    """
    def __init__(self, *args, **kwargs):
        super(UnrealEXRPublishPlugin, self).__init__(*args, **kwargs)
        print("PUBLISH_EXR INIT")

    @property
    def description(self):
        """
        Verbose, multi-line description of what the plugin does. This can
        contain simple html for formatting.
        """

        return """
        Publishes the sequence as an EXR image sequence to ShotGrid. A <b>Publish</b> 
        entry will be created in ShotGrid which will include a reference to the image
        sequence path on disk. A <b>Version</b> entry will also be created in ShotGrid 
        with the first frame being uploaded for review purposes.
        <br><br>
        EXR sequences will be rendered using the Movie Render Queue with high-quality
        settings and multi-channel support for maximum flexibility in compositing.
        """

    @property
    def settings(self):
        """
        Dictionary defining the settings that this plugin expects to receive
        through the settings parameter in the accept, validate, publish and
        finalize methods.
        """
        # inherit the settings from the base publish plugin
        base_settings = super(UnrealEXRPublishPlugin, self).settings or {}

        # Settings specific to this plugin
        exr_publish_settings = {
            "Publish Template": {
                "type": "template",
                "default": None,
                "description": "Template path for published EXR sequences. Should"
                             "correspond to a template defined in templates.yml.",
            },
            "Render Preset": {
                "type": "string",
                "default": None,
                "description": "Optional path to Movie Pipeline render preset"
            },
            "Frame Rate": {
                "type": "int",
                "default": 24,
                "description": "Frame rate for the rendered sequence"
            },
            "Resolution": {
                "type": "dict",
                "default": {"width": 1920, "height": 1080},
                "description": "Resolution for the rendered sequence"
            }
        }

        base_settings.update(exr_publish_settings)
        return base_settings

    @property
    def item_filters(self):
        """
        List of item types that this plugin is interested in.
        """
        return ["unreal.asset.LevelSequence"]

    def accept(self, settings, item):
        """
        Method called by the publisher to determine if an item is of any
        interest to this plugin. Only items matching the filters defined via the
        item_filters property will be presented to this method.
        """
        accepted = True

        publisher = self.parent
        template_name = settings["Publish Template"].value
        if template_name:
            publish_template = publisher.get_template_by_name(template_name)
            self.logger.debug("Checking template: %s" % publish_template)
            if not publish_template:
                self.logger.debug(
                    "A publish template could not be determined for the "
                    "item. Not accepting the item."
                )
                accepted = False
        else:
            self.logger.debug("No template provided. Not accepting the item.")
            accepted = False

        if not hasattr(unreal, "MoviePipelineQueueEngineSubsystem"):
            self.logger.warning(
                "Movie Render Queue is required for EXR sequence rendering. "
                "Please ensure you are using Unreal Engine 4.26 or later."
            )
            accepted = False

        # We've validated the publish template. Add it to the item properties
        if accepted:
            item.properties["publish_template"] = publish_template

        return {
            "accepted": accepted,
            "checked": True
        }

    def validate(self, settings, item):
        """
        Validates the given item to check that it is ok to publish.
        """
        asset_path = item.properties.get("asset_path")
        asset_name = item.properties.get("asset_name")
        if not asset_path or not asset_name:
            self.logger.debug("Sequence path or name not configured.")
            return False

        # Get the path in a normalized state
        path = sgtk.util.ShotgunPath.normalize(item.properties["path"])
        
        # Check that the parent folder exists
        folder = os.path.dirname(path)
        if not os.path.exists(folder):
            try:
                os.makedirs(folder)
            except OSError as e:
                self.logger.error(
                    "Failed to create parent folder for EXR sequence: %s" % str(e)
                )
                return False

        return True

    def publish(self, settings, item):
        """
        Executes the publish logic for the given item and settings.
        """
        publisher = self.parent
        
        # Get the path in a normalized state
        path = sgtk.util.ShotgunPath.normalize(item.properties["path"])
        
        # Ensure the parent folder exists
        folder = os.path.dirname(path)
        publisher.ensure_folder_exists(folder)

        # Configure and execute the EXR render
        try:
            self._render_exr_sequence(path, settings, item)
        except Exception as e:
            self.logger.error("Failed to render EXR sequence: %s" % str(e))
            raise

        # Let the base class register the publish
        super(UnrealEXRPublishPlugin, self).publish(settings, item)

        # Create a Version entry linked with the publish
        self._create_version(settings, item)

    def _render_exr_sequence(self, output_path, settings, item):
        """
        Renders the sequence to EXR using Movie Render Queue.
        """
        # Configure Movie Pipeline for EXR output
        qsub = unreal.MoviePipelineQueueEngineSubsystem()
        queue = qsub.get_queue()
        job = queue.allocate_new_job(unreal.MoviePipelineExecutorJob)
        
        # Set sequence and map
        job.sequence = unreal.SoftObjectPath(item.properties["asset_path"])
        job.map = unreal.SoftObjectPath(item.properties["unreal_map_path"])

        # Configure the job settings
        config = job.get_configuration()
        
        # Set up EXR output settings
        output_setting = config.find_or_add_setting_by_class(
            unreal.MoviePipelineImageSequenceOutput_EXR
        )
        output_setting.output_directory = unreal.DirectoryPath(os.path.dirname(output_path))
        output_setting.file_name_format = os.path.splitext(os.path.basename(output_path))[0]
        
        # Configure resolution
        resolution = settings["Resolution"].value
        output_setting.output_resolution = unreal.IntPoint(
            resolution["width"],
            resolution["height"]
        )

        # Set frame rate
        output_setting.output_frame_rate = unreal.FrameRate(settings["Frame Rate"].value)
        output_setting.use_custom_frame_rate = True
        
        # Configure EXR-specific settings
        output_setting.compression = unreal.EXRCompressionFormat.ZIP
        output_setting.bit_depth = unreal.EXRBitDepth.BIT_DEPTH_32
        
        # Add render passes for various AOVs
        render_pass = config.find_or_add_setting_by_class(
            unreal.MoviePipelineDeferredPassBase
        )
        render_pass.output_data = {
            "Beauty": True,
            "DiffuseColor": True,
            "Normals": True,
            "WorldPosition": True,
            "AmbientOcclusion": True
        }

        # Execute the render
        manifest_path = self._execute_render_queue(queue)
        
        # Wait for completion and verify output
        if not os.path.exists(output_path):
            raise RuntimeError("Failed to generate EXR sequence at: %s" % output_path)

    def _execute_render_queue(self, queue):
        """
        Executes the render queue and returns the manifest path.
        """
        _, manifest_path = unreal.MoviePipelineEditorLibrary.save_queue_to_manifest_file(queue)
        
        # Execute the queue in a separate process
        cmdline_args = [
            sys.executable,
            "-ExecutePipeline",
            "-RenderOffscreen",
            manifest_path
        ]
        
        # Run the render process
        subprocess.call(cmdline_args)
        
        return manifest_path

    def _create_version(self, settings, item):
        """
        Creates a Version entry in ShotGrid.
        """
        publisher = self.parent
        
        # Get the path in a normalized state
        path = sgtk.util.ShotgunPath.normalize(item.properties["path"])
        
        # Get the publish data
        publish_data = item.properties.get("sg_publish_data")
        
        # Create the version
        version_data = {
            "project": item.context.project,
            "code": item.name,
            "description": item.description,
            "entity": self._get_version_entity(item),
            "sg_path_to_frames": path,
            "sg_status_list": "rev",
            "sg_task": item.context.task
        }
        
        if publish_data:
            version_data["published_files"] = [publish_data]
        
        version = publisher.shotgun.create("Version", version_data)
        
        # Upload the first frame for review
        first_frame = self._get_first_frame(path)
        if first_frame:
            publisher.shotgun.upload(
                "Version",
                version["id"],
                first_frame,
                "sg_uploaded_movie"
            )
        
        return version

    def _get_first_frame(self, path):
        """
        Returns the path to the first frame in the sequence.
        """
        import glob
        
        seq_pattern = "%s.*" % os.path.splitext(path)[0]
        frames = sorted(glob.glob(seq_pattern))
        
        if frames:
            return frames[0]
        return None

    def _get_version_entity(self, item):
        """
        Returns the best entity to link the version to.
        """
        if item.context.entity:
            return item.context.entity
        elif item.context.project:
            return item.context.project
        else:
            return None
