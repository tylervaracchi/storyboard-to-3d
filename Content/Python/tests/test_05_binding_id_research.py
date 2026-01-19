# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
Test 05: MovieSceneObjectBindingID Research
Deep investigation of the binding ID structure in UE 5.6
"""

import unreal

def research_binding_id_structure():
    """Research the MovieSceneObjectBindingID structure and requirements"""

    unreal.log("Researching MovieSceneObjectBindingID structure...")

    try:
        # Create a MovieSceneObjectBindingID
        binding_id = unreal.MovieSceneObjectBindingID()

        unreal.log(f"Created binding ID: {binding_id}")
        unreal.log(f"Type: {type(binding_id)}")

        # Check all attributes
        unreal.log("\n    Attributes:")
        for attr in dir(binding_id):
            if not attr.startswith('_'):
                try:
                    value = getattr(binding_id, attr)
                    if not callable(value):
                        unreal.log(f"{attr}: {value} (type: {type(value).__name__})")
                except:
                    pass

        # Check all methods
        unreal.log("\n    Methods:")
        for method in dir(binding_id):
            if not method.startswith('_') and not method.startswith('get_') and not method.startswith('set_'):
                try:
                    attr = getattr(binding_id, method)
                    if callable(attr):
                        unreal.log(f"{method}()")
                except:
                    pass

        # Check editor properties
        if hasattr(binding_id, 'get_editor_property_names'):
            unreal.log("\n    Editor Properties:")
            props = binding_id.get_editor_property_names()
            for prop in props:
                try:
                    value = binding_id.get_editor_property(prop)
                    unreal.log(f"{prop}: {value} (type: {type(value).__name__})")
                except:
                    unreal.log(f"{prop}: <unable to get>")

        # Test setting properties
        unreal.log("\n    Testing property setters:")

        # Create a test GUID
        test_guid = unreal.Guid()
        unreal.log(f"Created test GUID: {test_guid}")

        # Try different ways to set the GUID
        success = False

        # Method 1: Direct attribute
        try:
            binding_id.guid = test_guid
            unreal.log("Direct attribute assignment works")
            success = True
        except Exception as e:
            unreal.log(f"Direct attribute failed: {str(e)[:50]}")

        # Method 2: set_editor_property
        try:
            binding_id.set_editor_property('guid', test_guid)
            unreal.log("set_editor_property('guid') works")
            success = True
        except Exception as e:
            unreal.log(f"set_editor_property failed: {str(e)[:50]}")

        # Test MovieSceneSequenceID
        unreal.log("\n    Testing MovieSceneSequenceID:")
        try:
            seq_id = unreal.MovieSceneSequenceID()
            unreal.log(f"Created: {seq_id}")

            # Check its properties
            if hasattr(seq_id, 'value'):
                unreal.log(f"Has 'value' attribute: {seq_id.value}")

            if hasattr(seq_id, 'get_editor_property_names'):
                props = seq_id.get_editor_property_names()
                unreal.log(f"Editor properties: {props}")

            # Try to set value
            try:
                seq_id.value = 0
                unreal.log("Can set value directly")
            except:
                try:
                    seq_id.set_editor_property('value', 0)
                    unreal.log("Can set value via editor property")
                except:
                    unreal.log("Cannot set value")

        except Exception as e:
            unreal.log(f"MovieSceneSequenceID error: {e}")

        # Test MovieSceneObjectBindingSpace
        unreal.log("\n    Testing MovieSceneObjectBindingSpace:")
        try:
            # Check if enum exists
            if hasattr(unreal, 'MovieSceneObjectBindingSpace'):
                unreal.log("MovieSceneObjectBindingSpace exists")

                # List enum values
                for attr in dir(unreal.MovieSceneObjectBindingSpace):
                    if not attr.startswith('_'):
                        value = getattr(unreal.MovieSceneObjectBindingSpace, attr)
                        if not callable(value):
                            unreal.log(f"- {attr}: {value}")

                # Test setting space
                try:
                    binding_id.space = unreal.MovieSceneObjectBindingSpace.LOCAL
                    unreal.log("Can set space directly")
                except:
                    try:
                        binding_id.set_editor_property('space', unreal.MovieSceneObjectBindingSpace.LOCAL)
                        unreal.log("Can set space via editor property")
                    except:
                        unreal.log("Cannot set space")
            else:
                unreal.log("MovieSceneObjectBindingSpace not found")

        except Exception as e:
            unreal.log(f"Space enum error: {e}")

        # Create a complete binding ID
        unreal.log("\n    Creating complete binding ID:")
        try:
            complete_binding = unreal.MovieSceneObjectBindingID()

            # Set all properties we can
            if hasattr(complete_binding, 'guid'):
                complete_binding.guid = test_guid
            elif hasattr(complete_binding, 'set_editor_property'):
                complete_binding.set_editor_property('guid', test_guid)

            if hasattr(unreal, 'MovieSceneSequenceID'):
                seq_id = unreal.MovieSceneSequenceID()
                if hasattr(seq_id, 'value'):
                    seq_id.value = 0
                elif hasattr(seq_id, 'set_editor_property'):
                    seq_id.set_editor_property('value', 0)

                if hasattr(complete_binding, 'sequence_id'):
                    complete_binding.sequence_id = seq_id
                elif hasattr(complete_binding, 'set_editor_property'):
                    complete_binding.set_editor_property('sequence_id', seq_id)

            if hasattr(unreal, 'MovieSceneObjectBindingSpace'):
                if hasattr(complete_binding, 'space'):
                    complete_binding.space = unreal.MovieSceneObjectBindingSpace.LOCAL
                elif hasattr(complete_binding, 'set_editor_property'):
                    complete_binding.set_editor_property('space', unreal.MovieSceneObjectBindingSpace.LOCAL)

            unreal.log("Complete binding ID created successfully")
            unreal.log(f"Result: {complete_binding}")

        except Exception as e:
            unreal.log(f"Failed to create complete binding: {e}")

        return success

    except Exception as e:
        unreal.log_error(f"Research failed: {e}")
        return False
