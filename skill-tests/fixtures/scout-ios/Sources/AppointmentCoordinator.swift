import UIKit
import SwiftUI

class AppointmentCoordinator {
    weak var navigationController: UINavigationController?

    func routeToCheckout() {
        let host = UIHostingController(rootView: CheckoutView())
        navigationController?.pushViewController(host, animated: true)
    }

    func routeToDetails() {
        let vc = Bridge.module.instantiate(for: "AppointmentDetails")
        navigationController?.pushViewController(vc, animated: true)
    }
}

struct CheckoutView: View {
    var body: some View { Text("Checkout") }
}
