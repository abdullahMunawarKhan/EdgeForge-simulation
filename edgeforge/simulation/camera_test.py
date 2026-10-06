import carla
import random
import time
import cv2
import numpy as np


def main():

    client = carla.Client("127.0.0.1", 2000)
    client.set_timeout(10.0)

    world = client.get_world()
    blueprint_library = world.get_blueprint_library()

    vehicle = None
    camera = None

    latest_frame = None

    try:

        # --------------------------------
        # 1. Spawn vehicle
        # --------------------------------

        vehicle_bp = random.choice(
            blueprint_library.filter("vehicle.*")
        )

        spawn_points = world.get_map().get_spawn_points()

        vehicle = world.try_spawn_actor(
            vehicle_bp,
            random.choice(spawn_points)
        )

        if vehicle is None:
            print("❌ Vehicle could not be spawned.")
            return

        print(f"✅ Vehicle spawned: {vehicle.type_id}")

        # --------------------------------
        # 2. Create RGB camera
        # --------------------------------

        camera_bp = blueprint_library.find(
            "sensor.camera.rgb"
        )

        camera_bp.set_attribute(
            "image_size_x",
            "640"
        )

        camera_bp.set_attribute(
            "image_size_y",
            "480"
        )

        camera_bp.set_attribute(
            "fov",
            "90"
        )

        camera_transform = carla.Transform(
            carla.Location(
                x=1.5,
                z=2.4
            )
        )

        camera = world.spawn_actor(
            camera_bp,
            camera_transform,
            attach_to=vehicle
        )

        print("✅ RGB camera attached.")

        # --------------------------------
        # 3. Camera callback
        # --------------------------------

        def process_image(image):

            nonlocal latest_frame

            array = np.frombuffer(
                image.raw_data,
                dtype=np.uint8
            )

            array = np.reshape(
                array,
                (image.height, image.width, 4)
            )

            # CARLA BGRA → OpenCV BGR
            latest_frame = array[:, :, :3].copy()

        camera.listen(process_image)

        print("📷 Camera streaming...")
        print("Press Q to stop.")

        # --------------------------------
        # 4. Main display loop
        # --------------------------------

        start_time = time.time()

        while time.time() - start_time < 60:

            if latest_frame is not None:

                cv2.imshow(
                    "EDGEFORGE - CARLA Camera",
                    latest_frame
                )

            key = cv2.waitKey(1) & 0xFF

            if key == ord("q"):
                break

            time.sleep(0.01)

    finally:

        # --------------------------------
        # 5. Cleanup
        # --------------------------------

        if camera is not None:
            camera.stop()
            camera.destroy()

        if vehicle is not None:
            vehicle.destroy()

        cv2.destroyAllWindows()

        print("🧹 Simulation actors cleaned up.")


if __name__ == "__main__":
    main()

    