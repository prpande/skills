// SwiftUI hosting controller for the appointment details screen.
class AppointmentDetailsHostingController: UIHostingController<AppointmentDetailsView> {
    required init?(coder: NSCoder) {
        super.init(coder: coder, rootView: AppointmentDetailsView())
    }
}
